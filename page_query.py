"""
curl 'https://api.notion.com/v1/pages/b55c9c91-384d-452b-81db-d1ef79372b75' \
  -H 'Notion-Version: 2025-09-03' \
  -H 'Authorization: Bearer '"$NOTION_API_KEY"''
"""
import requests
import json

def page_query(page_id):
    NOTION_API_KEY = "ntn_T91055169669oBLa2bqxGdKcT1J3IJs5f2rkJGi3osw1wc"
    # page_id = "2a721ebb-29a6-80f1-9c81-d2587347f3cc"
    # 设置请求的URL
    url = f"https://api.notion.com/v1/pages/{page_id}"
    # 设置请求头
    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Notion-Version': '2025-09-03'
    }
    # 发送GET请求
    response = requests.get(url, headers=headers)
    # 检查响应状态码
    if response.status_code == 200:
        data = response.json()
        print(f"Data from page {page_id}:")
        print(data)

    else:
        print(f"Failed to retrieve data from page {page_id}. Status code: {response.status_code}")

    # print(response.text)
    return response.json()