"""
curl 'https://api.notion.com/v1/blocks/b55c9c91-384d-452b-81db-d1ef79372b75/children?page_size=100' \
  -H 'Authorization: Bearer '"$NOTION_API_KEY"'' \
  -H "Notion-Version: 2022-06-28"
"""

import requests
import json
import time

def block_children_query(block_id):
    NOTION_API_KEY = "ntn_T91055169669oBLa2bqxGdKcT1J3IJs5f2rkJGi3osw1wc"
    # block_id = "b55c9c91-384d-452b-81db-d1ef79372b75"
    # 设置请求的URL
    url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
    # 设置请求头
    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Notion-Version': '2025-09-03'
    }
    # 发送GET请求
    for _ in range(5):
        try:
            response = requests.get(url, headers=headers)
            # 检查响应状态码
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                print(f"Failed to retrieve data from block {block_id}. Status code: {response.status_code}")
                time.sleep(10)
                
        except Exception as e:
            print(f"Error occurred: {e}, retrying...")
            time.sleep(10)
    return None

if __name__ == "__main__":
    block_id = "2a721ebb-29a6-80f1-9c81-d2587347f3cc"
    data = block_children_query(block_id)
    print(data)