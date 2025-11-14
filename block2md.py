import json
from typing import List, Dict, Any


def extract_text_content(rich_text_list: List[Dict[str, Any]]) -> str:
    """
    从rich_text列表中提取文本内容
    
    Args:
        rich_text_list: Notion的rich_text数组
        
    Returns:
        拼接后的纯文本字符串
    """
    if not rich_text_list:
        return ""
    
    text_parts = []
    for text_obj in rich_text_list:
        if text_obj.get("type") == "text":
            content = text_obj.get("text", {}).get("content", "")
            annotations = text_obj.get("annotations", {})
            
            # 应用markdown格式
            if annotations.get("bold"):
                content = f"**{content}**"
            if annotations.get("italic"):
                content = f"*{content}*"
            if annotations.get("strikethrough"):
                content = f"~~{content}~~"
            if annotations.get("code"):
                content = f"`{content}`"
            
            text_parts.append(content)
    
    return "".join(text_parts)


def notion_blocks_to_markdown(blocks: List[Dict[str, Any]]) -> str:
    """
    将Notion blocks转换为Markdown文本
    
    Args:
        blocks: Notion API返回的blocks数组
        
    Returns:
        转换后的Markdown文本
    """
    markdown_lines = []
    
    for block in blocks:
        block_type = block.get("type")
        
        if block_type == "heading_1":
            text = extract_text_content(block["heading_1"]["rich_text"])
            if text:
                markdown_lines.append(f"# {text}\n")
        
        elif block_type == "heading_2":
            text = extract_text_content(block["heading_2"]["rich_text"])
            if text:
                markdown_lines.append(f"## {text}\n")
        
        elif block_type == "heading_3":
            text = extract_text_content(block["heading_3"]["rich_text"])
            if text:
                markdown_lines.append(f"### {text}\n")
        
        elif block_type == "paragraph":
            text = extract_text_content(block["paragraph"]["rich_text"])
            if text:
                markdown_lines.append(f"{text}\n")
            else:
                markdown_lines.append("\n")
        
        elif block_type == "to_do":
            text = extract_text_content(block["to_do"]["rich_text"])
            checked = block["to_do"]["checked"]
            checkbox = "[x]" if checked else "[ ]"
            if text:
                markdown_lines.append(f"- {checkbox} {text}\n")
        
        elif block_type == "bulleted_list_item":
            text = extract_text_content(block["bulleted_list_item"]["rich_text"])
            if text:
                markdown_lines.append(f"- {text}\n")
        
        elif block_type == "numbered_list_item":
            text = extract_text_content(block["numbered_list_item"]["rich_text"])
            if text:
                markdown_lines.append(f"1. {text}\n")
        
        elif block_type == "code":
            text = extract_text_content(block["code"]["rich_text"])
            language = block["code"].get("language", "")
            if text:
                markdown_lines.append(f"```{language}\n{text}\n```\n")
        
        elif block_type == "quote":
            text = extract_text_content(block["quote"]["rich_text"])
            if text:
                markdown_lines.append(f"> {text}\n")
        
        elif block_type == "divider":
            markdown_lines.append("---\n")
    
    return "".join(markdown_lines)


# 使用示例
if __name__ == "__main__":
    # 从文件读取JSON数据
    with open("tmp.json", "r", encoding="utf-8") as f:
        blocks = json.load(f)
    
    # 转换为Markdown
    markdown_text = notion_blocks_to_markdown(blocks)
    
    # 打印结果
    print(markdown_text)
    
    # 可选：保存到文件
    with open("output.md", "w", encoding="utf-8") as f:
        f.write(markdown_text)