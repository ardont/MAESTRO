import sys
import json
import time

try:
    from RLT_project.rag.main_rag import rag_pipeline
    
    print('Testing RAG Pipeline...')
    t0 = time.time()
    result = rag_pipeline('Как подать жалобу в ФАС?')
    
    print('\n================ RESULT ================')
    print('ANSWER:', result.get('answer', ''))
    print('\nSOURCES:')
    for doc in result.get('sources', []):
        print(doc.get('title'), doc.get('url'), doc.get('score'))
    
    print('\nTIMINGS:', result.get('timings', {}))
except Exception as e:
    print('Error:', e)
