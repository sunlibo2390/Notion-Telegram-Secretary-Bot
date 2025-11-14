from openai import OpenAI
client = OpenAI(api_key='sk-r6ehOERZyG6WdIgiF6B5A380F94142218f06D83418A7EcDe',
                   base_url='https://api.ai-gaochao.cn/v1')


def text_query(query):
    response = client.chat.completions.create(
        # model="gemini-2.5-pro",
        model="gpt-5-chat-latest",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query}
        ]
    )
    # 判断response是否正常返回
    if response and response.choices:
        reply = response.choices[0].message.content
        return reply
    return None


if __name__ == "__main__":
    response = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Who won the world series in 2020?"}
    ]
    )
    # 判断response是否正常返回
    if response and response.choices:
        reply = response.choices[0].message.content
        # print(reply)

    
    # print(response)
    print(response.choices[0].message.content)