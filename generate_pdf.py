import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register Cyrillic Font
pdfmetrics.registerFont(TTFont('ArialCustom', 'C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold', 'C:/Windows/Fonts/arialbd.ttf'))

doc_path = r"c:\Users\Maxim\Desktop\фокусы\хакатоны\рлт\агентная система поддержки\Tender_Hack_Architecture_Plan.pdf"
doc = SimpleDocTemplate(
    doc_path,
    pagesize=A4,
    rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
)

styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle(
    'TitleStyle',
    parent=styles['Normal'],
    fontName='ArialBold',
    fontSize=22,
    leading=26,
    textColor=colors.HexColor('#1A237E'),
    spaceAfter=10
)

subtitle_style = ParagraphStyle(
    'SubtitleStyle',
    parent=styles['Normal'],
    fontName='ArialCustom',
    fontSize=12,
    leading=16,
    textColor=colors.HexColor('#37474F'),
    spaceAfter=15
)

h1_style = ParagraphStyle(
    'H1Style',
    parent=styles['Normal'],
    fontName='ArialBold',
    fontSize=14,
    leading=18,
    textColor=colors.HexColor('#0D47A1'),
    spaceBefore=12,
    spaceAfter=8
)

body_style = ParagraphStyle(
    'BodyStyle',
    parent=styles['Normal'],
    fontName='ArialCustom',
    fontSize=10,
    leading=14,
    textColor=colors.HexColor('#212121'),
    spaceAfter=6
)

bullet_style = ParagraphStyle(
    'BulletStyle',
    parent=styles['Normal'],
    fontName='ArialCustom',
    fontSize=9.5,
    leading=13.5,
    textColor=colors.HexColor('#263238'),
    leftIndent=12,
    spaceAfter=4
)

table_header_style = ParagraphStyle(
    'TableHeader',
    parent=styles['Normal'],
    fontName='ArialBold',
    fontSize=10,
    leading=13,
    textColor=colors.white
)

elements = []

# Title Banner
elements.append(Paragraph("TENDER HACK 2026 — АРХИТЕКТУРНЫЙ ПЛАН ПОБЕДИТЕЛЯ", title_style))
elements.append(Paragraph("<b>Тема:</b> Автоматизация работы с запросами пользователей в службу поддержки с помощью ИИ<br/><b>Целевая платформа:</b> Портал поставщиков Москвы (zakupki.mos.ru)<br/><b>Формат архитектуры:</b> Enterprise Multi-Agent RAG System (1 месяц разработки)", subtitle_style))
elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1A237E'), spaceAfter=15))

# Section 1: Ключевые требования и стратегия
elements.append(Paragraph("1. Стратегическое позиционирование решения", h1_style))
elements.append(Paragraph("Для победы в соревновании B2G формата недостаточно простой RAG-системы. Жюри оценивает готовность решения к внедрению в реальный бизнес-контур Портала поставщиков. Система должна гарантировать 0% галлюцинаций, мгновенную блокировку нецензурных обращений, точную маршрутизацию по линиям L1-L3 и глубинный аналитический модуль для руководителей.", body_style))

# Section 2: 5 Killer-фич
elements.append(Paragraph("2. Топ-5 Архитектурных Преимуществ (Killer Features)", h1_style))

features = [
    ("1. Auto-Export в BPMN 2.0", "Код графа агентной системы (LangGraph) автоматически экспортируется в валидный XML BPMN 2.0 для Camunda/Bizagi. Полное соответствие регламентам Департамента по конкурентной политике."),
    ("2. Strict Fallback (NO_INFO)", "Если в БЗ нет ответа с высоким коэффициентом уверенности (>0.72), модель выдает статус NO_INFO и с немедленной переадресацией на оператора 1-й линии."),
    ("3. Guardrail & Toxicity Gatekeeper", "Двухуровневый фильтр мата (RegEx + ruBERT-tiny2) за < 5 мс завершает токсичные сессии, формирует официальное предупреждение и фиксирует инцидент в аудит-логе."),
    ("4. Smart Router (L1 / L2 / L3)", "Автоматическая классификация обращений: L1 (Общие/FAQ), L2 (Технические сбои, ЭЦП, КриптоПро), L3 (Юридические вопросы 44-ФЗ/223-ФЗ, финансовые спецсчета)."),
    ("5. Root Cause PDF Analytics", "Анализ отзывов (1-5 звезд). LLM-воркер выявляет системные проблемы работы операторов и формирует содержательные PDF-заключения с инсайтами для менеджмента.")
]

for title, desc in features:
    elements.append(Paragraph(f"• <b>{title}:</b> {desc}", bullet_style))

elements.append(Spacer(1, 10))

# Section 3: Спринты разработки (Таблица)
elements.append(Paragraph("3. Дорожная карта разработки на 4 недели (Дорожная карта победы)", h1_style))

table_data = [
    [
        Paragraph("Неделя", table_header_style),
        Paragraph("Спринт / Фокус", table_header_style),
        Paragraph("Результат и Ключевые Задачи", table_header_style)
    ],
    [
        Paragraph("<b>Неделя 1</b>", body_style),
        Paragraph("Data & Hybrid RAG Foundation", body_style),
        Paragraph("Парсинг методичек, гибридный поиск (BM25 + Dense Vectors + BGE Reranker), протокол защиты от галлюцинаций NO_INFO.", body_style)
    ],
    [
        Paragraph("<b>Неделя 2</b>", body_style),
        Paragraph("Multi-Agent Core & Routing", body_style),
        Paragraph("Сборка графа LangGraph, Gatekeeper токсичности, Диспетчер линий L1-L3, транслятор графа в BPMN 2.0 XML.", body_style)
    ],
    [
        Paragraph("<b>Неделя 3</b>", body_style),
        Paragraph("Analytics & Voice (ASR)", body_style),
        Paragraph("Аналитический модуль оценки работы операторов, генерация PDF-отчетов системных проблем, голосовой ввод (Whisper/Vosk).", body_style)
    ],
    [
        Paragraph("<b>Неделя 4</b>", body_style),
        Paragraph("UI/UX & Benchmarking", body_style),
        Paragraph("Двоякий Web UI (Чат-виджет для поставщиков + Дашборд руководителя), проведение бенчмарков, подготовка презентации.", body_style)
    ]
]

t = Table(table_data, colWidths=[65, 135, 320])
t.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0D47A1')),
    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#B0BEC5')),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ('TOPPADDING', (0, 0), (-1, -1), 6),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
]))
elements.append(t)

elements.append(Spacer(1, 15))
elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#B0BEC5'), spaceAfter=10))
elements.append(Paragraph("<i>Сформировано автоматически AI-Ассистентом Antigravity в рамках подготовки к хакатону Tender Hack 2026.</i>", ParagraphStyle('Foot', parent=styles['Normal'], fontName='ArialCustom', fontSize=8, textColor=colors.gray)))

doc.build(elements)
print("PDF created successfully at:", doc_path)
