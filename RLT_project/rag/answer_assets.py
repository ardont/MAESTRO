"""Keep retrieved sources and illustrations in the persisted Markdown answer."""
import os
from urllib.parse import urlsplit, quote


def format_answer_assets(result):
    answer = result['answer']
    links = []
    for citation in result.get('citations', []):
        url = citation.get('url', '')
        if urlsplit(url).scheme not in ('http', 'https') or url in answer:
            continue
        title = str(citation.get('title') or 'Источник').replace('[', '').replace(']', '')
        link = f'- [{title}]({quote(url, safe=":/?=&%#")})'
        if link not in links:
            links.append(link)
    if links:
        answer += '\n\n**Источники из базы знаний:**\n' + '\n'.join(links)
    images = []
    for raw in result.get('images', []):
        if not isinstance(raw, str):
            continue
        url = raw
        if urlsplit(url).scheme not in ('http', 'https'):
            # Local assets are served by memory-api; expose the public address via env.
            path = raw.lstrip('/')
            if path.startswith(('media/', 'images/')) and '..' not in path.split('/'):
                url = os.environ.get('RAG_PUBLIC_URL', 'http://localhost:8989').rstrip('/') + '/' + path
            else:
                continue
        if url not in images and url not in answer:
            images.append(url)
    if images:
        answer += '\n\n**Иллюстрации к инструкции:**\n\n' + '\n\n'.join(
            f'![Иллюстрация {i}]({quote(url, safe=":/?=&%#")})' for i, url in enumerate(images, 1)
        )
    return answer
