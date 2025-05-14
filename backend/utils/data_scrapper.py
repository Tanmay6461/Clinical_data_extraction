
import argparse
import requests
import time
import os
import re
from bs4 import BeautifulSoup
import json
from gcp.cloud_storage import upload_file, read_json_from_gcs, write_json_to_gcs
from io import BytesIO, StringIO
from google.oauth2 import service_account
from utils.litellm.helper import prompt_get_drug_names, prompt_group_drug_names, final_drug_info_schema, prompt_summarize_drug_data
from utils.litellm.llm import llm
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from jsonschema import validate, ValidationError
import shutil


class SECFilingExtractor:
    """Class to download and extract content from SEC filings."""
    
    # SEC API endpoints
    BASE_URL = "https://data.sec.gov"
    SUBMISSIONS_ENDPOINT = "/submissions/CIK{}.json"
    BUCKET_NAME = os.getenv('GCP_BUCKET_NAME')


    def __init__(self, ticker, email, output_dir="sec_extracts"):
        """Initialize the extractor with a ticker symbol."""
        self.ticker = ticker.upper()
        self.cik = None
        self.output_dir = output_dir
        self.email = email
        
        # Required headers for SEC API requests
        self.headers = {
            "User-Agent": f"SECFilingExtractor {email}",
            "Accept-Encoding": "gzip, deflate"
        }
        
        self.cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self.credentials = service_account.Credentials.from_service_account_file(self.cred_path)

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Rate limiting - SEC allows max 10 requests per second
        self.request_interval = 0.1
        self.last_request_time = 0
        
        # Track extracted filings
        self.extracted_8k = []
        self.extracted_10k = []
        self.extracted_10q = []
    
    def _enforce_rate_limit(self):
        """Enforce SEC's rate limit of 10 requests per second."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.request_interval:
            time.sleep(self.request_interval - time_since_last_request)
        
        self.last_request_time = time.time()
    
    def get_cik_from_ticker(self):
        """Get the CIK number for the given ticker symbol."""
        url = "https://www.sec.gov/files/company_tickers_exchange.json"
        
        try:
            self._enforce_rate_limit()
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            # Process the data structure with 'fields' and 'data' arrays
            if 'fields' in data and 'data' in data:
                # Get index of 'ticker' and 'cik' in fields
                ticker_index = data['fields'].index('ticker') if 'ticker' in data['fields'] else None
                cik_index = data['fields'].index('cik') if 'cik' in data['fields'] else None
                
                if ticker_index is not None and cik_index is not None:
                    # Search for our ticker in the data array
                    for company in data['data']:
                        if company[ticker_index] == self.ticker:
                            # Found the company, extract CIK and pad to 10 digits
                            self.cik = str(company[cik_index]).zfill(10)
                            return self.cik
            
            # If we reach here, ticker wasn't found
            return None
            
        except Exception as e:
            print(f"Error getting CIK for {self.ticker}: {e}")
            return None
        
    def get_filings(self, form_types=("8-K", "10-K", "10-Q")):
        """Get all specified filings for the ticker."""
        if not self.cik:
            self.get_cik_from_ticker()
            if not self.cik:
                raise ValueError(f"Could not find CIK for ticker: {self.ticker}")
        
        # Construct URL for submissions endpoint
        url = f"{self.BASE_URL}{self.SUBMISSIONS_ENDPOINT.format(self.cik)}"
        
        # Get submission data
        try:
            self._enforce_rate_limit()
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            filings = []
            
            # Process recent filings
            if "filings" in data and "recent" in data["filings"]:
                recent = data["filings"]["recent"]
                
                # Check if we have the necessary arrays
                required_keys = ["form", "accessionNumber", "filingDate", "primaryDocument"]
                if all(k in recent for k in required_keys):
                    for i in range(len(recent["form"])):
                        if i < len(recent["accessionNumber"]) and i < len(recent["filingDate"]) and i < len(recent["primaryDocument"]):
                            if recent["form"][i] in form_types:
                                filing = {
                                    "accessionNumber": recent["accessionNumber"][i],
                                    "form": recent["form"][i],
                                    "filingDate": recent["filingDate"][i],
                                    "primaryDocument": recent["primaryDocument"][i],
                                    "description": recent.get("description", [""])[i] if i < len(recent.get("description", [])) else ""
                                }
                                filings.append(filing)
            
            # Group filings by type
            filing_counts = {form_type: len([f for f in filings if f["form"] == form_type]) for form_type in form_types}
            for form_type, count in filing_counts.items():
                print(f"Found {count} {form_type} filings")
            
            return filings
            
        except Exception as e:
            print(f"Error getting filings: {e}")
            return []
    
    def download_filing_content(self, filing):
        """Download a filing and get its raw text."""
        acc_no = filing["accessionNumber"].replace('-', '')
        
        # Construct the URL for the filing document
        url = f"https://www.sec.gov/Archives/edgar/data/{self.cik.lstrip('0')}/{acc_no}/{filing['primaryDocument']}"
        
        try:
            self._enforce_rate_limit()
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
            
            # Get text content
            text = soup.get_text()
            
            # Clean text - remove excessive whitespace
            lines = [line.strip() for line in text.split('\n')]
            text = '\n'.join(line for line in lines if line)
            
            return text, url
            
        except Exception as e:
            print(f"Error downloading filing {filing['accessionNumber']}: {e}")
            return None, None
    
    def process_filing(self, filing, form_type):
        """
        Process an SEC filing, extract sections based on form type, and upload directly to GCS.
        
        Args:
            filing (dict): Filing information dictionary
            form_type (str): Type of form ('8-K', '10-K', or '10-Q')
            credentials: Google Cloud credentials (required)
            
        Returns:
            bool: True if processing was successful, False otherwise
        """
        os.environ["LITELLM_VERBOSE"] = "False"
        if not self.credentials:
            print("Error: GCP credentials are required for direct GCS upload")
            return False
        
        # Download filing content
        text, url = self.download_filing_content(filing)
        
        if not text:
            return False
        
        # Extract sections based on form type
        sections = {}
        if form_type == '8-K':
            sections = self.extract_8k_items(text)
        else:  # 10-K or 10-Q
            sections = self.extract_filing_sections(text, form_type=form_type)
        
        if not sections:
            print(f"No sections found in {form_type} filing {filing['accessionNumber']}")
            return False
        
        # Generate filename for GCS
        filename = f"{self.ticker}_{form_type}_{filing['filingDate']}_{filing['accessionNumber']}.txt"
        
        # GCS path - organize by ticker/form_type/year/filename
        filing_year = filing['filingDate'].split('-')[0]  # Extract year from filing date
        gcs_filename = f"{self.ticker}/{form_type}/{filing_year}/{filename}"
        
        # Prepare file content in memory
        content = StringIO()
        
        # Write filing metadata
        content.write(f"TICKER: {self.ticker}\n")
        content.write(f"CIK: {self.cik}\n")
        content.write(f"FORM TYPE: {form_type}\n")
        content.write(f"FILING DATE: {filing['filingDate']}\n")
        content.write(f"ACCESSION NUMBER: {filing['accessionNumber']}\n")
        content.write(f"URL: {url}\n")
        content.write("-" * 80 + "\n\n")
        
        # Write sections with appropriate formatting based on form type
        if form_type == '8-K':
            # 8-K: Write each item with its own header
            for item_number, item_content in sections.items():
                content.write(f"{item_number}\n")
                content.write("-" * 40 + "\n")
                content.write(item_content)
                content.write("\n\n" + "=" * 80 + "\n\n")
        else:
            # 10-K/10-Q: section with a clear header
            for section_name, section_text in sections.items():
                content.write("\n" + "=" * 80 + "\n")
                content.write(f"{section_name}\n")
                content.write("=" * 80 + "\n\n")
                content.write(section_text)
                content.write("\n\n")


        formatted_prompt =  prompt_get_drug_names.format(
        ticker=self.ticker,
        content=content.getvalue()
        )


        # drug_facts = {} 
        llm_response = llm(
            model="vertex_ai/gemini-2.5-pro-preview-05-06",
            # model="vertex_ai/gemini-2.5-flash-preview-04-17",
            prompt=formatted_prompt, 
        )   

        raw_response = llm_response['response'].strip()
        
        if not raw_response:
            print(f"Empty LLM response for {filing['form']} - skipping.")
            return None
        
        # print('raw', raw_response)

        if raw_response.startswith("```json"):
            raw_response = raw_response.removeprefix("```json").removesuffix("```").strip()
        elif raw_response.startswith("```"):
            raw_response = raw_response.removeprefix("```").removesuffix("```").strip()

        try:
            parsed_response = json.loads(raw_response)
        except json.JSONDecodeError as e:
            print(f"Could not parse LLM JSON: {e}")
         
            return None

        # Upload to GCS
        try:
            # Convert StringIO to BytesIO for upload
            content_bytes = BytesIO(content.getvalue().encode('utf-8'))
            content.close()
            
            upload_response = upload_file(
                file_data=content_bytes,
                filename=gcs_filename,
                content_type='text/plain',
                credentials=self.credentials
            )
            
            if  upload_response == 1:
                gcs_url = f"gs://{self.BUCKET_NAME}/{gcs_filename}"
                print(f"Uploaded {form_type} filing to GCS: {gcs_url}")
                
                # Save filing info to appropriate list
                filing_info = {
                    "filingDate": filing["filingDate"],
                    "accessionNumber": filing["accessionNumber"],
                    "url": url,
                    "gcsUrl": gcs_url
                }
                
                # Add form-specific fields and save to appropriate list
                if form_type == '8-K':
                    self.extracted_8k.append(filing_info)
                elif form_type == '10-K':
                    self.extracted_10k.append(filing_info)
                elif form_type == '10-Q':
                    self.extracted_10q.append(filing_info)
                else:
                    print(f"Unknown form type {form_type} - not saving.")   
            else :
                print(f"Failed to upload {form_type} filing to GCS: {gcs_filename}")
                return False    
            
            self.save_structured_metadata()
            return parsed_response

        except Exception as e:
            print(f"Error uploading to GCS: {e}")
            return False

    def extract_8k_items(self, text):
        """
        Extract all item sections from an 8-K filing.
        Returns a dictionary with item numbers as keys and their content as values.
        """
        # Pattern to match item sections in 8-K filings (e.g., "Item 1.01", "Item 7.01")
        item_pattern = r'(?:^|\n)(?:Item\s+(\d+\.\d+)[^\n]*)'
        
        # Find all item matches
        matches = list(re.finditer(item_pattern, text, re.IGNORECASE | re.MULTILINE))
        
        if not matches:
            # logging.warning("No item sections found in the 8-K filing")
            return {}
        
        # Extract each item section
        items = {}
        for i, match in enumerate(matches):
            item_number = match.group(1)  # Extract the item number (e.g., "1.01")
            section_start = match.start()
            
            # Determine section end (next item or end of text)
            if i < len(matches) - 1:
                section_end = matches[i + 1].start()
            else:
                # Look for SIGNATURES section
                sig_match = re.search(r'SIGNATURES?', text[section_start:], re.IGNORECASE)
                if sig_match:
                    section_end = section_start + sig_match.start()
                else:
                    # If SIGNATURES not found, extract until the end
                    section_end = len(text)
            
            # Extract and clean section text
            section_text = text[section_start:section_end].strip()
            
            # Store the section with its item number as key
            items[f"Item {item_number}"] = section_text
        
        return items
    
    def extract_filing_sections(self, text, form_type='10-K'):
        """
        Generic function to extract sections from SEC filings (10-K, 10-Q).
    
        """
        
        # Define section patterns based on form type
        if form_type == '10-K':
            target_sections = [
                r'Item\s+1\.\s+Business',
                r'Item\s+1A\.\s+Risk\s+Factors',
                r'Item\s+2\.\s+Properties',
                r'Item\s+3\.\s+Legal\s+Proceedings',
                r'Item\s+4\.\s+Mine\s+Safety\s+Disclosures',
                # r'Item\s+5\.\s+Market\s+for\s+Registrant',
                # r'Item\s+6\.\s+Selected\s+Financial\s+Data',
                r'Item\s+7\.\s+Management\'s\s+Discussion',
                # r'Item\s+8\.\s+Financial\s+Statements',
                r'Item\s+9A\.\s+Controls\s+and\s+Procedures',
                r'Item\s+9B\.\s+Other\s+Information',
                # r'Item\s+15\.\s+Exhibits',
                r'Item\s+16\.\s+10K-Summary'
            ]
        elif form_type == '10-Q':
            target_sections = [
                # r'Item\s+1\.\s+Financial\s+Statements',
                r'Item\s+2\.\s+Management\'s\s+Discussion',
                # r'Item\s+3\.\s+Quantitative\s+and\s+Qualitative\s+Disclosures',
                # r'Item\s+4\.\s+Controls\s+and\s+Procedures',
                r'Item\s+1\.\s+Legal\s+Proceedings',
                r'Item\s+1A\.\s+Risk\s+Factors',
                # r'Item\s+2\.\s+Unregistered\s+Sales',
                r'Item\s+3\.\s+Defaults\s+Upon\s+Senior\s+Securities',
                r'Item\s+4\.\s+Mine\s+Safety\s+Disclosures',
                r'Item\s+5\.\s+Other\s+Information',
                # r'Item\s+6\.\s+Exhibits',
                # r'Part\s+I\.\s+Financial\s+Information',
                r'Part\s+II\.\s+Other\s+Information'
            ]
        else:
            return {}  # Unsupported form type
        
        # Pattern to match any target section
        section_pattern = '|'.join(target_sections)
        
        # Find all section matches
        matches = list(re.finditer(section_pattern, text, re.IGNORECASE))
        
        if not matches:
            return {}
        # Extract each section
        sections = {}
        for i, match in enumerate(matches):
            section_start = match.start()
            section_title = text[match.start():match.end()].strip()
            
            # Determine section end (next section or end of text)
            if i < len(matches) - 1:
                section_end = matches[i + 1].start()
            else:
                # Look for common end markers
                end_markers = ['SIGNATURES', 'SIGNATURE', 'EXHIBITS', 'PART IV']
                end_pos = float('inf')
                
                for marker in end_markers:
                    marker_pos = text.find(marker, section_start)
                    if marker_pos != -1 and marker_pos < end_pos:
                        end_pos = marker_pos
                
                section_end = end_pos if end_pos < float('inf') else len(text)
            
            # Extract and clean section text
            section_text = text[section_start:section_end].strip()
            
            # Get simplified section name based on form type
            if form_type == '10-K':
                section_name = re.match(r'(Item\s+\d+\.?[A-Z]?\.\s+[^\.]+)', section_title, re.IGNORECASE)
            else:  # 10-Q
                section_name = re.match(r'((?:Part|Item)\s+[IiVv]+\.?|Item\s+\d+\.?[A-Z]?\.\s+[^\.]+)', section_title, re.IGNORECASE)
                
            if section_name:
                section_name = section_name.group(1).strip()
            else:
                section_name = section_title
            
            sections[section_name] = section_text
        
        return sections
    
    def save_structured_metadata(self):
        """Save structured data of all extracted filings to JSON."""
        try:
            index_data= {
                    "ticker": self.ticker,
                    "cik": self.cik,
                    "counts": {
                        "8K": len(self.extracted_8k),
                        "10K": len(self.extracted_10k),
                        "10Q": len(self.extracted_10q)
                    },
                    "filings": {
                        "8K": self.extracted_8k,
                        "10K": self.extracted_10k,
                        "10Q": self.extracted_10q
                    }
                }
            
            index_content = json.dumps(index_data, indent=2).encode('utf-8')
            file_data = BytesIO(index_content)
            index_gcs_path = f"{self.ticker}/{self.ticker}_filings_index.json"
            
            store_metadata = upload_file(
                file_data=file_data,
                filename=index_gcs_path,
                content_type='application/json',
                credentials= self.credentials
            )
            return {
                "status_code": 200,
                "message":"Combined index file stored to GCS" 
                    }
        
        except Exception as e:
                return f"Error processing filings: {str(e)}"
        
    def merge_all_drug_data(self, drug_facts_path, alias_groups):
        """
        Merge drug data based on alias groups to consolidate information.

        """
        try:
            # Load original drug facts
            with open(drug_facts_path, "r", encoding="utf-8") as f:
                drug_facts_data = json.load(f)
            
            # Create alias to canonical name mapping in one pass
            alias_to_main = {}
            canonical_aliases = {}
            
            for group in alias_groups:
                canonical = group["name"]
                aliases = set(alias.strip().lower() for alias in group.get("aliases", []))
                
                # Store original aliases for later (avoid re-processing)
                canonical_aliases[canonical] = sorted(group.get("aliases", []))
                
                # Add self-mapping
                alias_to_main[canonical.strip().lower()] = canonical
                
                # Add all aliasesd =
                for alias in aliases:
                    alias_to_main[alias] = canonical
            
            # Process drug data - use direct dictionary manipulation instead of defaultdict
            merged_data = {}
            drugs_section = drug_facts_data.get("drugs", {})
            
            for drug_name, facts in drugs_section.items():
                # Get canonical name, defaulting to original if no match
                drug_key = drug_name.strip().lower()
                canonical = alias_to_main.get(drug_key, drug_name)
                
                # Initialize dictionary for this canonical drug if needed
                if canonical not in merged_data:
                    merged_data[canonical] = {}
                
                # Merge all facts
                for field, value in facts.items():
                    if field not in merged_data[canonical]:
                        # Initialize the field with an empty set
                        merged_data[canonical][field] = set()
                    
                    # Add values depending on type
                    if isinstance(value, list):
                        merged_data[canonical][field].update(value)
                    elif isinstance(value, str):
                        merged_data[canonical][field].add(value)
            
            # Build final output with sorted lists
            final_output = {"drugs": {}}
            
            for drug, data in merged_data.items():
                final_output["drugs"][drug] = {
                    field: sorted(list(values)) for field, values in data.items()
                }
                
                # Add aliases if this is a canonical drug
                if drug in canonical_aliases:
                    final_output["drugs"][drug]["aliases"] = canonical_aliases[drug]
            
            return final_output
        except Exception as e:
            print(f"Error merging drug data: {e}")
            return None

    def group_and_merge_drug_aliases(self, partial_path: str) -> dict:
        with open(partial_path, "r") as f:
            data = json.load(f)
        print(f"[Alias Merge] Loaded {len(data.get('drugs', {}))} drugs from partial data.")
        drugs_info = []
        for drug_name, drug_data in data.get("drugs", {}).items():
            aliases = drug_data.get("aliases", [])
            drugs_info.append({
                "name": drug_name,
                "aliases": aliases
            })

        drugs_info_json = json.dumps(drugs_info, indent=2)
        formatted_prompt = prompt_group_drug_names.format(content=drugs_info_json)

        response = llm(model="vertex_ai/gemini-2.5-flash-preview-04-17", prompt=formatted_prompt)
        raw_response = response["response"].strip()

        if raw_response.startswith("```json"):
            raw_response = raw_response.removeprefix("```json").removesuffix("```").strip()
        elif raw_response.startswith("```"):
            raw_response = raw_response.removeprefix("```").removesuffix("```").strip()

        try:
            canonical_mapping = json.loads(raw_response)
        except json.JSONDecodeError as e:
            print(f"[Alias Merge] Failed to parse LLM response: {e}")
            raise

        final_merge = self.merge_all_drug_data(partial_path, canonical_mapping)
        return final_merge

    def process_all_filings(self, form_types=("8-K", "10-K", "10-Q"), max_workers=35, override_filings=None):
        try:
            if override_filings:
                filings = override_filings
            else:
                filings = self.get_filings(form_types)

            print(f"Processing {len(filings)} filings...")

            # Resume from partial
            partial_path = os.path.join(self.output_dir, f"{self.ticker}_drug_facts_partial.json")
            drug_facts = defaultdict(lambda: defaultdict(set))

            if os.path.exists(partial_path):
                with open(partial_path, "r") as f:
                    raw_data = json.load(f)
                for drug, fact_map in raw_data.get("drugs", {}).items():
                    for fact_type, values in fact_map.items():
                        if isinstance(values, list):
                            drug_facts[drug][fact_type].update(values)

            # Internal helper to process one filing
            def handle_filing(filing):
                try:
                    form_type = filing["form"]
                    data = self.process_filing(filing, form_type)
                    return filing, data
                except Exception as e:
                    return filing, None

            # Threaded execution
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(handle_filing, filing) for filing in filings]
                # futures = [executor.submit(handle_filing, filings[0])]

                for i, future in enumerate(as_completed(futures), 1):
                    filing, data = future.result()
                    print(f"Finished {i}/{len(filings)}: {filing['accessionNumber']}")

                    if data and "programs" in data:
                        for program in data["programs"]:
                            if not isinstance(program, dict):
                                continue
                            drug_name = program.get("name", "UNKNOWN").strip("'\" ")
                            if not drug_name:
                                continue
                            for fact_type, fact_value in program.items():
                                if fact_type == "name":
                                    continue
                                if isinstance(fact_value, list):
                                    clean = [v for v in fact_value if isinstance(v, str)]
                                    drug_facts[drug_name][fact_type].update(clean)
                                elif isinstance(fact_value, str) and fact_value.strip():
                                    drug_facts[drug_name][fact_type].add(fact_value)

                    # Save intermediate
                    tmp_result = {
                        "drugs": {
                            drug: {
                                fact_type: sorted(list(fact_set))
                                for fact_type, fact_set in fact_types.items()
                            }
                            for drug, fact_types in drug_facts.items()
                        }
                    }

                    with open(partial_path, "w") as f:
                        json.dump(tmp_result, f, indent=2)
           
            final_merge = self.group_and_merge_drug_aliases(partial_path)
            json_str = json.dumps(final_merge, indent=2)
            file_data = BytesIO(json_str.encode("utf-8"))
            gcs_filename = f"{self.ticker}/{self.ticker}_drug_facts.json"


            #validating output schema 
            try:
                validate(instance=final_merge, schema=final_drug_info_schema)
                print("Schema validation passed.")
            except ValidationError as ve:
                raise ValueError(f"Schema validation failed: {ve.message}")
            

            store_drug_name = upload_file(
                file_data=file_data,
                filename=gcs_filename,
                content_type="application/json",
                credentials=self.credentials
            )

            # self.save_structured_metadata()

            if os.path.exists(partial_path):
                os.remove(partial_path)

            return {
                "status_code": 200,
                "message": "Upload successful" if store_drug_name == 1 else "Upload failed"
            }

        except Exception as e:
            print(f"Error processing filings: {e}")
            return False

    def process_new_filings_only(self, form_types=("8-K", "10-K", "10-Q"), max_workers=35, state_path=None):
        # GCS-based state file path
        state_blob_path = f"{self.ticker}/track_{self.ticker}_filings.json"

        # Step 1: Read processed accession numbers from GCS
        try:
            processed = read_json_from_gcs(self.BUCKET_NAME, state_blob_path, self.credentials)
        except Exception as e:
            print(f"Failed to read processed accessions: {e}")
            processed = set()

        all_filings = self.get_filings(form_types=form_types)
        new_filings = [f for f in all_filings if f["accessionNumber"] not in processed]
        if not new_filings:
            print("No new filings to process.")
            return
        
        print(f"Found {len(new_filings)} new filings.")
        self.process_all_filings(form_types=form_types, max_workers=max_workers, override_filings=new_filings)

        try:
            new_processed = processed.union(f["accessionNumber"] for f in new_filings)
            write_json_to_gcs(self.BUCKET_NAME, state_blob_path, new_processed, self.credentials)
            print("Updated processed accessions in GCS.")
        except Exception as e:
            print(f"Failed to update processed accessions in GCS: {e}")
        
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
            print(f"Deleted output_dir: {self.output_dir}")
            
