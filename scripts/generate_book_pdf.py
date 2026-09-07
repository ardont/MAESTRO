"""
generate_book_pdf.py — Генератор книги в формате PDF из Markdown-руководства.

Использует ReportLab 5.0+, кириллические шрифты Arial/Arial-Bold,
формирует обложку в стиле O'Reilly / Manning, оглавление, нумерацию страниц,
акцентные блоки (Callout boxes), форматирование таблиц и кода.
"""

import os
import sys
import re
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, HRFlowable, ListFlowable, ListItem
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily


# ==============================================================================
# ШРИФТЫ И ДВУХПРОХОДНАЯ НУМЕРАЦИЯ СТРАНИЦ
# ==============================================================================

def setup_fonts():
    font_dir = "C:/Windows/Fonts"
    pdfmetrics.registerFont(TTFont('Arial', f'{font_dir}/arial.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Bold', f'{font_dir}/arialbd.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Italic', f'{font_dir}/ariali.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-BoldItalic', f'{font_dir}/arialbi.ttf'))
    registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic', boldItalic='Arial-BoldItalic')


class NumberedCanvas(canvas.Canvas):
    """Двухпроходный канвас для вычисления точного общего числа страниц 'Стр. X из Y'."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        if self._pageNumber == 1:
            # Обложка — без колонтитулов
            return

        self.saveState()
        self.setFont("Arial", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Верхний колонтитул
        self.drawString(54, A4[1] - 36, "RLT.Tender_Guide: Архитектура и реализация RAG-системы")
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(54, A4[1] - 42, A4[0] - 54, A4[1] - 42)

        # Нижний колонтитул
        page_text = f"Страница {self._pageNumber} из {page_count}"
        self.drawRightString(A4[0] - 54, 36, page_text)
        self.drawString(54, 36, "Практика построения прикладных LLM-систем (2026)")
        self.line(54, 46, A4[0] - 54, 46)

        self.restoreState()


# ==============================================================================
# СТИЛИ ДОКУМЕНТА
# ==============================================================================

def create_styles():
    base = getSampleStyleSheet()
    
    styles = {
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            fontName="Arial-Bold",
            fontSize=28,
            leading=34,
            textColor=colors.HexColor("#0f172a"),
            alignment=0, # лево
            spaceAfter=12
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            fontName="Arial",
            fontSize=15,
            leading=20,
            textColor=colors.HexColor("#334155"),
            spaceAfter=25
        ),
        "CoverSeries": ParagraphStyle(
            "CoverSeries",
            fontName="Arial-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#2563eb"),
            textTransform="uppercase",
            spaceAfter=15
        ),
        "CoverAuthor": ParagraphStyle(
            "CoverAuthor",
            fontName="Arial",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#475569"),
            spaceAfter=6
        ),
        "PartBanner": ParagraphStyle(
            "PartBanner",
            fontName="Arial-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#ffffff"),
            spaceBefore=0,
            spaceAfter=0
        ),
        "ChapterHeading": ParagraphStyle(
            "ChapterHeading",
            fontName="Arial-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=18,
            spaceAfter=10,
            keepWithNext=True
        ),
        "SubHeading": ParagraphStyle(
            "SubHeading",
            fontName="Arial-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=14,
            spaceAfter=6,
            keepWithNext=True
        ),
        "Body": ParagraphStyle(
            "Body",
            fontName="Arial",
            fontSize=10,
            leading=14.5,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=8,
            alignment=4 # Justify
        ),
        "BulletText": ParagraphStyle(
            "BulletText",
            fontName="Arial",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#334155"),
            spaceAfter=4
        ),
        "CalloutText": ParagraphStyle(
            "CalloutText",
            fontName="Arial-Italic",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#1e3a8a"),
        ),
        "CodeText": ParagraphStyle(
            "CodeText",
            fontName="Arial",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#0f172a"),
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            fontName="Arial-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#ffffff"),
            alignment=1 # Center
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            fontName="Arial",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1e293b")
        )
    }
    return styles


# ==============================================================================
# ПАРСЕР MARKDOWN В FLOWABLES
# ==============================================================================

def make_callout(text, styles, width=A4[0]-108):
    p = Paragraph(f"<b>Примечание архитектора:</b> {text}", styles["CalloutText"])
    t = Table([[p]], colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#eff6ff")),
        ('LEFTPADDING', (0,0), (-1,-1), 14),
        ('RIGHTPADDING', (0,0), (-1,-1), 14),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LINELEFT', (0,0), (0,-1), 3.5, colors.HexColor("#2563eb")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#bfdbfe")),
    ]))
    return t

def make_part_banner(title, styles, width=A4[0]-108):
    p = Paragraph(title.upper(), styles["PartBanner"])
    t = Table([[p]], colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0f172a")),
        ('LEFTPADDING', (0,0), (-1,-1), 16),
        ('RIGHTPADDING', (0,0), (-1,-1), 16),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ]))
    return t

def make_code_block(code_lines, styles, width=A4[0]-108):
    escaped = "<br/>".join(
        line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;")
        for line in code_lines
    )
    p = Paragraph(f"<font face='Arial'>{escaped}</font>", styles["CodeText"])
    t = Table([[p]], colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
    ]))
    return t


def parse_markdown_to_flowables(md_text: str, styles) -> list:
    flowables = []
    lines = md_text.splitlines()
    in_code_block = False
    code_buffer = []
    
    # 1. Формирование титульной страницы (Cover Page)
    flowables.append(Spacer(1, 40))
    
    # Декоративная полоса
    dec_bar = Table([[""]], colWidths=[60], rowHeights=[6])
    dec_bar.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#2563eb"))]))
    flowables.append(dec_bar)
    flowables.append(Spacer(1, 15))

    flowables.append(Paragraph("ПРАКТИКА ПОСТРОЕНИЯ ПРИКЛАДНЫХ LLM-СИСТЕМ", styles["CoverSeries"]))
    flowables.append(Paragraph("RLT.Tender_Guide:<br/>Архитектура и реализация промышленной агентной RAG-системы", styles["CoverTitle"]))
    flowables.append(Paragraph("Практическое руководство по созданию отказоустойчивых интеллектуальных ассистентов в сфере регламентированных госзакупок (44-ФЗ, 223-ФЗ, Портал Поставщиков Москвы)", styles["CoverSubtitle"]))
    
    flowables.append(Spacer(1, 60))
    flowables.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=20))
    flowables.append(Paragraph("<b>Авторы:</b> Команда разработки RLT.Tender_Guide", styles["CoverAuthor"]))
    flowables.append(Paragraph("<b>Рецензенты:</b> Эксперты по прикладным нейросетевым технологиям", styles["CoverAuthor"]))
    flowables.append(Paragraph("<b>Издание:</b> Первое издание, переработанное и дополненное (2026)", styles["CoverAuthor"]))
    flowables.append(Paragraph("<b>Стек:</b> Python 3.10 • Django 4.2 • Qdrant Hybrid • PyTorch CUDA • Ollama Qwen2.5:7B", styles["CoverAuthor"]))
    flowables.append(PageBreak())

    # 2. Парсинг контента
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        
        # Блоки кода
        if line.startswith("```"):
            if in_code_block:
                flowables.append(make_code_block(code_buffer, styles))
                flowables.append(Spacer(1, 8))
                code_buffer = []
                in_code_block = False
            else:
                in_code_block = True
            idx += 1
            continue

        if in_code_block:
            code_buffer.append(lines[idx])
            idx += 1
            continue

        # Пустые строки
        if not line:
            idx += 1
            continue

        # Горизонтальный разделитель
        if line in ("---", "***", "___"):
            flowables.append(Spacer(1, 6))
            flowables.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=10))
            idx += 1
            continue

        # Цитаты / Примечания
        if line.startswith(">"):
            quote_text = line.lstrip("> ").strip()
            # Форматируем markdown bold
            quote_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', quote_text)
            flowables.append(make_callout(quote_text, styles))
            flowables.append(Spacer(1, 8))
            idx += 1
            continue

        # Части (Баннеры ЧАСТЬ I, ЧАСТЬ II...)
        if line.startswith("## ЧАСТЬ"):
            part_title = line.lstrip("# ").strip()
            flowables.append(Spacer(1, 14))
            flowables.append(make_part_banner(part_title, styles))
            flowables.append(Spacer(1, 14))
            idx += 1
            continue

        # Главы (## ГЛАВА X...)
        if line.startswith("### ГЛАВА") or line.startswith("## ГЛАВА"):
            ch_title = line.lstrip("# ").strip()
            flowables.append(Spacer(1, 10))
            flowables.append(Paragraph(ch_title, styles["ChapterHeading"]))
            flowables.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2563eb"), spaceAfter=12))
            idx += 1
            continue

        # Подразделы (#### 1.1...)
        if line.startswith("#### ") or line.startswith("### "):
            sub_title = line.lstrip("# ").strip()
            flowables.append(Paragraph(sub_title, styles["SubHeading"]))
            idx += 1
            continue

        # Маркированные списки
        if line.startswith("- ") or line.startswith("* "):
            bullet_text = line[2:].strip()
            bullet_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', bullet_text)
            bullet_text = re.sub(r'`(.*?)`', r'<font face="Arial" color="#2563eb">\1</font>', bullet_text)
            bullet_p = Paragraph(f"• &nbsp; {bullet_text}", styles["BulletText"])
            flowables.append(bullet_p)
            idx += 1
            continue

        # Нумерованные списки
        num_match = re.match(r'^(\d+)\.\s+(.*)$', line)
        if num_match:
            num = num_match.group(1)
            item_text = num_match.group(2)
            item_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', item_text)
            item_text = re.sub(r'`(.*?)`', r'<font face="Arial" color="#2563eb">\1</font>', item_text)
            p = Paragraph(f"<b>{num}.</b> &nbsp; {item_text}", styles["BulletText"])
            flowables.append(p)
            idx += 1
            continue

        # Обычный параграф текста
        para_text = line
        para_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', para_text)
        para_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', para_text)
        para_text = re.sub(r'`(.*?)`', r'<font face="Arial" color="#1e40af"><b>\1</b></font>', para_text)
        
        flowables.append(Paragraph(para_text, styles["Body"]))
        idx += 1

    return flowables


# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ
# ==============================================================================

def build_pdf_book(md_path: str, output_pdf_path: str):
    setup_fonts()
    styles = create_styles()

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    flowables = parse_markdown_to_flowables(md_text, styles)

    print(f"[PDF] Сборка документа: {output_pdf_path}...")
    doc.build(flowables, canvasmaker=NumberedCanvas)
    print(f"[PDF] ✅ Книга успешно сгенерирована: {output_pdf_path}")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    md_file = base_dir / "docs" / "rlt_tender_guide_handbook.md"
    out_pdf = base_dir / "RLT_Tender_Guide_Book.pdf"

    build_pdf_book(str(md_file), str(out_pdf))
