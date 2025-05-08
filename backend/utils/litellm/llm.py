from litellm import completion
from datetime import datetime
from io import StringIO



def llm(model, prompt):

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
            'prompt': prompt, 
            'response': response.choices[0].message.content,
            'model' : response.model,
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens' : response.usage.completion_tokens,
            'created' : datetime.fromtimestamp(response.created).strftime('%Y-%m-%d %H:%M:%S')
            }