
import argparse
import requests
import time
import os
import re
from bs4 import BeautifulSoup
import json
from backend.gcp.cloud_storage import upload_file
from io import BytesIO, StringIO
from google.oauth2 import service_account
from backend.utils.litellm.helper import prompt_get_drug_names
from backend.utils.litellm.llm import llm
import ast

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
        
        # cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        # credentials = service_account.Credentials.from_service_account_file(cred_path)
      
        drug_names = set()


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
            # 10-K/10-Q: Write each section with a clear header
            for section_name, section_text in sections.items():
                content.write("\n" + "=" * 80 + "\n")
                content.write(f"{section_name}\n")
                content.write("=" * 80 + "\n\n")
                content.write(section_text)
                content.write("\n\n")


        formatted_prompt =  prompt_get_drug_names.format(
        # form_type=form_type,
        ticker=self.ticker,
        content=content.getvalue()
        )


        llm_reponse = llm(
            model="vertex_ai/gemini-2.0-flash-001",
            prompt=formatted_prompt, 
            # response_format= {}
        )   

        response_content = llm_reponse['response']
        try:
            drugs = ast.literal_eval(response_content.strip())
            for drug in drugs:
                drug_names.add(drug)
        except Exception as e:
            print(f"Could not parse drug names: {e}")
        
        drug_list = list(drug_names)

        # Upload to GCS
        try:
            # Convert StringIO to BytesIO for upload
            content_bytes = BytesIO(content.getvalue().encode('utf-8'))
            content.close()
            
            upload_result = upload_file(
                file_data=content_bytes,
                filename=gcs_filename,
                content_type='text/plain',
                credentials=self.credentials
            )
            
            if True: #upload_result == 1:
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
                
                return drug_list
            # else:
            #     print(f"Failed to upload {form_type} filing to GCS: {gcs_filename}")
            #     return False
                
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
        
        Args:
            text (str): The full text of the SEC filing
            form_type (str): The type of form ('10-K' or '10-Q')
            
        Returns:
            dict: A dictionary of section names and their contents
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
    
    def save_structured_data(self):
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
         

    def process_all_filings(self, form_types=("8-K", "10-K", "10-Q")):
        """Process all filings of the specified types."""
        try:
                # Get list of filings
                filings = self.get_filings(form_types)
                
                if not filings:
                    print(f"No filings found for {self.ticker}")
                    return
                
                print(f"Processing {len(filings)} filings...")

                unique_drugs = set()
                
                # Process each filing based on its type
                for filing in filings:
                    form_type = filing["form"]
                    
                    if form_type == "8-K":
                        data = self.process_filing(filing, '8-K')
                    elif form_type == "10-K":
                        data = self.process_filing(filing, '10-K')
                    elif form_type == "10-Q":
                        data = self.process_filing(filing, '10-Q')
                    

                    if data:
                        for drug in data:
                            unique_drugs.add(drug)
                    
                drugs_json = {"drugs": sorted(list(unique_drugs))}
                json_str = json.dumps(drugs_json, indent=2)
                file_data = BytesIO(json_str.encode('utf-8'))
                gcs_filename =  f"{self.ticker}/{self.ticker}_drug_names.json"


                store_drug_name = upload_file(
                    file_data=file_data,
                    filename=gcs_filename,
                    content_type='application/json', 
                    credentials=self.credentials
                )

                self.save_structured_data()

                if store_drug_name == 1:
                    return {
                        "status_code": 200,
                        "message":f"Successfully uploaded drug names for {self.ticker}"
                    }
                else:
                    return {
                        "status_code": 200,
                        "message":f"Failed to upload drug names for {self.ticker}"
                    }
        except Exception as e:
            print(f"Error processing filings: {str(e)}")
            return False


def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Extract content from SEC filings (8-K, 10-K, 10-Q).")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., WVE, DRNA, ALNY)")
    # parser.add_argument("email", help="Your email for SEC API access")
    parser.add_argument("--form-types", nargs="+", default=["8-K", "10-K", "10-Q"], 
                      help="Form types to process (default: 8-K, 10-K, 10-Q)")
    parser.add_argument("--output-dir", default="sec_extracts", 
                      help="Directory to save extracted content (default: sec_extracts)")
    
    args = parser.parse_args()
    
    print(f"Extracting {', '.join(args.form_types)} filings for {args.ticker}...")
    
    extractor = SECFilingExtractor(args.ticker, "thgfg@gmail.com", f"sec_data/{args.ticker}")
    extractor.process_all_filings(args.form_types)

if __name__ == "__main__":
    main()