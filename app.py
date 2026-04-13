import chainlit as cl  # create chat website 
from groq import Groq  # libraray to talk to groq models or api 
import os    # operating system 
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))  #os.get - fetch value id api key from .env then create an actual connection 


@cl.on_message
async def main(message: cl.Message):
    
    response = client.chat.completions.create(
      model="llama-3.3-70b-versatile" ,
        max_tokens=1000,
       
        #what messages does it feed history again and again for a continuity in conversation since usually grok every time u run its a fresh conversation it has no memeory 
        messages=[
            {
                "role": "system", #background inst that user never sees 
                "content": "You are a helpful AI assistant for entrepreneurs. You help them manage their calendar, networking, and daily tasks."
            },
            {
                "role": "user", #what human types 
                "content": message.content
            }
        ]
    )
    
    await cl.Message(content=response.choices[0].message.content).send()