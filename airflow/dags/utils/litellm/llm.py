from litellm import completion
from datetime import datetime
from io import StringIO
import os, json
from openai import OpenAI
from airflow.models import Variable

def llmlite(model, prompt):
    if isinstance(prompt, StringIO):
        prompt = prompt.getvalue()

    messages = [{"role": "user", "content": prompt}]
    response = completion(
        model=model,
        messages=messages,
        temperature=0.7,
        # max_tokens=1000
    )
    
    return {'id':response.id,
            'response': response.choices[0].message.content,
            'model' : response.model,
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens' : response.usage.completion_tokens,
            'created' : datetime.fromtimestamp(response.created).strftime('%Y-%m-%d %H:%M:%S')
            }



def llm(model, prompt, client):
    # openai.api_key = Variable.get("OPENAI_API_KEY")
    if isinstance(prompt, StringIO):
        prompt = prompt.getvalue()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
    except Exception as e:
        print(f"OpenAI API call failed: {e}")
        return None

    return {
        'id': response.id,
        'response': response.choices[0].message.content,
        'model': response.model,
        'prompt_tokens': response.usage.prompt_tokens,
        'completion_tokens': response.usage.completion_tokens,
        'created': datetime.fromtimestamp(response.created).strftime('%Y-%m-%d %H:%M:%S')
    }
