import os
import sys
import json
from openai import OpenAI
from typing import List, Dict, Tuple
import time
import math

# 获取项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 从环境变量读取模型名称，如果没有则使用默认值
MODEL_NAME = os.getenv('AI_MODEL_NAME', 'deepseek-chat')

def get_file_paths():
    """获取所有必要的文件路径"""
    root = project_root
    
    paths = {
        'json_input': os.path.join(root, 'data', 'raw', 'all_papers_unique.json'),
        'keywords': os.path.join(root, 'config', 'keywords.txt'),
        'json_output': os.path.join(root, 'data', 'raw', 'all_papers_feedback.json'),
        'progress_dir': os.path.join(root, 'scripts', 'temp_progress')
    }
    
    return paths

def load_keywords_config(keywords_path: str) -> Tuple[str, List[str]]:
    """加载关键词配置。

    支持两种写法：
    1) 显式前缀：
       - primary: agent
       - secondary: reliability
    2) 兼容旧写法：第一行视为primary，其余行视为secondary。
    """
    try:
        with open(keywords_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        primary_keyword = ""
        secondary_keywords: List[str] = []

        for raw_line in lines:
            if raw_line.startswith('#'):
                continue

            line = raw_line
            lower_line = line.lower()

            if lower_line.startswith('primary:') or lower_line.startswith('main:'):
                value = line.split(':', 1)[1].strip()
                if value and not primary_keyword:
                    primary_keyword = value
                elif value:
                    print(f"警告: 检测到多个主关键词，忽略后续主关键词: {value}")
                continue

            if (
                lower_line.startswith('secondary:')
                or lower_line.startswith('additional:')
                or lower_line.startswith('extra:')
            ):
                value = line.split(':', 1)[1].strip()
                if value:
                    secondary_keywords.append(value)
                continue

            # 兼容旧格式：首个关键词作为主关键词，剩余关键词作为附加关键词。
            if not primary_keyword:
                primary_keyword = line
            else:
                secondary_keywords.append(line)

        print(
            f"从 {keywords_path} 加载关键词配置: "
            f"主关键词={primary_keyword or '未设置'}, "
            f"附加关键词={len(secondary_keywords)} 个"
        )
        return primary_keyword, secondary_keywords
        
    except FileNotFoundError:
        print(f"警告: 关键词文件未找到 - {keywords_path}")
        return "moduli space", ["Conlumb branch", "Hodge theory"]
    except Exception as e:
        print(f"加载关键词错误: {e}")
        return "", []

def load_papers_from_json(file_path: str) -> List[Dict]:
    """从JSON文件加载论文数据
    
    假设文件包含论文字典列表，每个字典有id, title, authors, categories, abstract等字段
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            papers = json.load(f)
        
        if not isinstance(papers, list):
            raise ValueError("JSON文件应包含论文列表")
        
        print(f"成功加载 {len(papers)} 篇论文")
        return papers
            
    except Exception as e:
        print(f"加载论文数据错误: {e}")
        return []


def normalize_text(text: str) -> str:
    """统一文本格式，便于做关键词匹配。"""
    return (text or "").strip().lower()


def should_select_by_keywords(paper: Dict, primary_keyword: str, secondary_keywords: List[str]) -> bool:
    """本地规则：必须命中主关键词，且至少命中一个附加关键词。"""
    title = normalize_text(paper.get('title', ''))
    abstract = normalize_text(paper.get('abstract', ''))
    categories = " ".join(paper.get('categories', []))
    haystack = f"{title}\n{abstract}\n{normalize_text(categories)}"

    primary = normalize_text(primary_keyword)
    if not primary or primary not in haystack:
        return False

    normalized_secondary = [normalize_text(k) for k in secondary_keywords if normalize_text(k)]
    if not normalized_secondary:
        return False

    return any(kw in haystack for kw in normalized_secondary)


def build_summary_prompt(paper: Dict, primary_keyword: str, secondary_keywords: List[str]) -> str:
    """构造单篇精选论文的总结提示词。"""
    title = paper.get('title', 'N/A')
    authors = paper.get('authors', [])
    categories = paper.get('categories', [])
    abstract = paper.get('abstract', '')

    return f"""请总结以下数学论文（该论文已通过关键词筛选）：

标题: {title}
作者: {', '.join(authors) if authors else 'N/A'}
分类: {', '.join(categories) if categories else 'N/A'}
摘要: {abstract}

关键词规则:
- 主关键词(必须命中): {primary_keyword}
- 附加关键词(至少命中一个): {", ".join(secondary_keywords)}

请直接输出一段中文总结，要求：
1. 3-4句，简洁，不要照搬摘要。
2. 数学术语保持英文，使用英文标点。
3. 可使用$...$表示公式，确保可被常见LaTeX数学包编译。
4. 不要输出序号、标签或额外解释。
"""


def summarize_selected_paper(
    client: OpenAI,
    paper: Dict,
    primary_keyword: str,
    secondary_keywords: List[str],
    system_prompt: str
) -> str:
    """仅对精选论文调用API生成翻译/总结。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": build_summary_prompt(paper, primary_keyword, secondary_keywords)
        }
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.1,
        max_tokens=260,
        timeout=30
    )

    result = (response.choices[0].message.content or "").strip()
    if not result:
        return ""

    if hasattr(response, 'usage'):
        usage = response.usage
        print(f"Token使用: 输入={usage.prompt_tokens}, 输出={usage.completion_tokens}, 总计={usage.total_tokens}")

    return result

def process_all_papers(batch_size: int = 5) -> Tuple[List[Dict], int]:
    """
    先用关键词筛选精选，再仅对精选论文做AI总结
    
    Args:
        batch_size: 每批处理的论文数量（默认5篇）
        
    Returns:
        papers_with_feedback: 添加了 selected/comment 字段的论文列表
        selected_count: 被精选的论文数量（关键词筛选后）
    """
    # 获取文件路径
    paths = get_file_paths()
    
    # 加载论文数据
    print(f"正在加载论文数据从: {paths['json_input']}")
    all_papers = load_papers_from_json(paths['json_input'])
    
    if not all_papers:
        print("错误: 无法加载论文数据")
        return [], 0
    
    print(f"成功加载 {len(all_papers)} 篇论文")
    
    # 加载关键词配置
    primary_keyword, secondary_keywords = load_keywords_config(paths['keywords'])

    if not primary_keyword:
        print("警告: 未配置主关键词，使用默认主关键词 moduli space")
        primary_keyword = "moduli space"

    if not secondary_keywords:
        print("警告: 未配置附加关键词，使用默认附加关键词")
        secondary_keywords = ["Conlumb branch", "Hodge theory"]

    print(f"使用主关键词: {primary_keyword}")
    print(f"使用附加关键词({len(secondary_keywords)}个): {', '.join(secondary_keywords)}")
    print(f"开始进行关键词筛选，共 {len(all_papers)} 篇论文...\n")

    # 第一阶段：本地关键词筛选（不调用API）
    selected_indices = []
    for idx, paper in enumerate(all_papers):
        is_selected = should_select_by_keywords(paper, primary_keyword, secondary_keywords)
        paper['selected'] = is_selected
        # 只在精选论文上保存翻译；非精选论文清空comment
        paper['comment'] = ""
        if is_selected:
            selected_indices.append(idx)

    selected_count = len(selected_indices)
    print(f"关键词筛选完成：精选候选 {selected_count} 篇，非精选 {len(all_papers) - selected_count} 篇")

    if selected_count == 0:
        print("没有命中关键词的精选论文，跳过DeepSeek调用")
        try:
            with open(paths['json_output'], 'w', encoding='utf-8') as f:
                json.dump(all_papers, f, ensure_ascii=False, indent=2)
            print(f"结果已保存到: {paths['json_output']}")
        except Exception as e:
            print(f"保存结果文件错误: {e}")
        return all_papers, 0
    
    # 创建进度文件目录
    if not os.path.exists(paths['progress_dir']):
        os.makedirs(paths['progress_dir'])
        print(f"创建进度目录: {paths['progress_dir']}")

    # 第二阶段：仅对精选论文调用DeepSeek
    total_batches = math.ceil(selected_count / batch_size)
    print(f"开始生成精选论文翻译：共 {selected_count} 篇，将分 {total_batches} 批处理，每批 {batch_size} 篇")

    # 初始化客户端
    deepseek_key = os.environ.get('DEEPSEEK_API_KEY')

    if not deepseek_key:
        print("错误: 未设置 DEEPSEEK_API_KEY，无法生成精选论文翻译")
        try:
            with open(paths['json_output'], 'w', encoding='utf-8') as f:
                json.dump(all_papers, f, ensure_ascii=False, indent=2)
            print(f"已保存仅含筛选结果的数据: {paths['json_output']}")
        except Exception as e:
            print(f"保存结果文件错误: {e}")
        return all_papers, selected_count
    
    client = OpenAI(
        api_key=deepseek_key,
        base_url="https://api.deepseek.com",  # DeepSeek API 端点
    )
    
    # 系统提示：这里只做精选论文翻译/总结，不再输出打分
    system_prompt = """你是一位严格的数学学术专家。请仅输出中文总结。

要求：
1. 数学术语保持英文，使用英文标点符号。
2. 内容精炼，避免照搬摘要。
3. 可包含必要公式，使用$...$。
4. 不要输出标签、评分、前后缀解释。
"""

    processed_count = 0
    
    # 分批处理精选论文
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, selected_count)
        current_selected_indices = selected_indices[start_idx:end_idx]
        
        print(f"\n{'='*60}")
        print(f"处理批次 {batch_num+1}/{total_batches} (精选论文 {start_idx+1}-{end_idx})")
        print(f"{'='*60}")

        batch_done_count = 0

        for i, paper_idx in enumerate(current_selected_indices, 1):
            paper = all_papers[paper_idx]
            paper_global_idx = paper_idx + 1
            print(f"\n--- 精选论文 {start_idx + i}/{selected_count} (全量序号 {paper_global_idx}) ---")
            
            # 提取论文信息
            title = paper.get('title', 'N/A')
            authors = paper.get('authors', [])
            categories = paper.get('categories', [])
            abstract = paper.get('abstract', '')
            
            print(f"标题: {title}")
            print(f"作者: {', '.join(authors) if authors else 'N/A'}")
            print(f"分类: {', '.join(categories) if categories else 'N/A'}")
            print(f"摘要: {abstract[:200]}...")
            
            try:
                print("调用API生成精选论文翻译...")
                comment = summarize_selected_paper(
                    client,
                    paper,
                    primary_keyword,
                    secondary_keywords,
                    system_prompt
                )
                paper['comment'] = comment
                print(f"翻译:\n{comment}")

                processed_count += 1
                batch_done_count += 1

            except Exception as e:
                print(f"❌❌ API调用错误: {e}")
                # 保留精选标记，但评论置空，避免错误内容进入展示
                paper['comment'] = ""
                processed_count += 1
                batch_done_count += 1
            
            # 请求间延迟，避免速率限制
            if i < len(current_selected_indices):
                time.sleep(1)
        
        # 批次处理完成统计
        print(f"\n批次 {batch_num+1} 完成: 翻译了 {batch_done_count} 篇精选论文")
        
        # 保存当前进度（每批完成后保存）
        progress_file = os.path.join(paths['progress_dir'], f"processing_progress_batch_{batch_num+1}.json")
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump({
                "batch": batch_num + 1,
                "total_batches": total_batches,
                "processed_so_far": processed_count,
                "selected_so_far": selected_count,
                "selected_indices": selected_indices,
                "papers_snapshot": all_papers
            }, f, ensure_ascii=False, indent=2)
        
        print(f"进度已保存到: {progress_file}")
        
        # 批次间延迟
        if batch_num < total_batches - 1:
            print(f"等待3秒后处理下一批...")
            time.sleep(3)
    
    # 输出最终统计信息
    print(f"\n{'='*60}")
    print("所有论文处理完成!")
    print(f"{'='*60}")
    print(f"总论文数: {len(all_papers)}")
    print(f"已翻译精选论文数: {processed_count}")
    print(f"精选论文数: {selected_count}")
    print(f"精选比例: {selected_count/len(all_papers):.1%}" if len(all_papers) > 0 else "0%")
    
    # 显示精选论文
    if selected_count > 0:
        print(f"\n精选论文列表:")
        for i, paper in enumerate(all_papers, 1):
            if paper.get('selected', False):
                print(f"{i}. {paper.get('title', 'N/A')}")
    
    # 保存最终结果 - 只保存论文列表，不添加额外元数据
    try:
        with open(paths['json_output'], 'w', encoding='utf-8') as f:
            json.dump(all_papers, f, ensure_ascii=False, indent=2)
        
        print(f"\n完整结果已保存到: {paths['json_output']}")
        print(f"结果文件包含 {len(all_papers)} 篇论文，且仅精选论文带有comment")
        
    except Exception as e:
        print(f"保存结果文件错误: {e}")
    
    return all_papers, selected_count

if __name__ == "__main__":
    # 每批处理5篇“精选候选”论文
    papers_with_feedback, selected_count = process_all_papers(batch_size=5)
    
    if papers_with_feedback:
        print(f"\n处理完成！")
        print(f"总论文数: {len(papers_with_feedback)}")
        print(f"精选论文数: {selected_count}")
        print(f"精选比例: {selected_count/len(papers_with_feedback):.1%}")
        
        # 显示前几篇精选论文
        print(f"\n前5篇精选论文:")
        count = 0
        for paper in papers_with_feedback:
            if paper.get('selected', False):
                print(f"- {paper.get('title', 'N/A')}")
                count += 1
                if count >= 5:
                    break
    else:
        print("处理失败，没有生成结果")
