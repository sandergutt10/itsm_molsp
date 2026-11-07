"""
Утилиты для экспорта расписания в Excel и PDF.
Используется в Streamlit UI.
"""

import io
from datetime import datetime

# Excel
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)

# Цвета по приоритетам
PRIORITY_COLORS = {
    "critical": ("FF4444", colors.red),
    "high": ("FF8800", colors.orange),
    "medium": ("FFCC00", colors.yellow),
    "low": ("88CC88", colors.lightgreen),
}

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Регистрация шрифтов
pdfmetrics.registerFont(TTFont("RussianFont", FONT_REGULAR))
pdfmetrics.registerFont(TTFont("RussianFont-Bold", FONT_BOLD))

# Объединение в семейство
pdfmetrics.registerFontFamily(
    "RussianFont",
    normal="RussianFont",
    bold="RussianFont-Bold",
    italic="RussianFont",
    boldItalic="RussianFont-Bold",
)

def export_excel(schedule_data: dict) -> bytes:
    """
    Экспортирует расписание в Excel.
    Возвращает bytes готового .xlsx файла.

    schedule_data — ответ от /schedule эндпоинта оркестратора.
    """
    wb = Workbook()

    # --- Лист 1: Расписание по слотам ---
    ws = wb.active
    ws.title = "Расписание"

    # Стили
    header_font = Font(bold=True, size=12, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F5496")
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # Заголовок
    ws.merge_cells("A1:F1")
    ws["A1"] = "Расписание работ на день (MOLSP)"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 30

    # Метаданные
    ws["A2"] = "Дата формирования:"
    ws["B2"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws["A3"] = "Статус решения:"
    ws["B3"] = schedule_data.get("status", "?")
    ws["A4"] = "Суммарный штраф:"
    ws["B4"] = schedule_data.get("total_penalty", 0)
    ws["A5"] = "Макс. загрузка:"
    ws["B5"] = f"{schedule_data.get('max_load', 0)} слотов"

    for row in range(2, 6):
        ws[f"A{row}"].font = Font(bold=True)

    # Заголовки таблицы
    headers = ["Слот", "Час", "Инженер", "Заявка", "Приоритет", "Заголовок", "SLA"]
    start_row = 7
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    # Данные
    assignments = schedule_data.get("assignments", [])
    sorted_a = sorted(assignments, key=lambda x: (x["slot"], x["engineer"]))

    for i, a in enumerate(sorted_a):
        row = start_row + 1 + i
        values = [
            a["slot"] + 1,
            f"Час {a['slot'] + 1}",
            a["engineer"],
            a["task_id"],
            a["priority"],
            a["title"][:60],
            "OK" if a["sla_ok"] else "VIOLATION",
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = border
            cell.alignment = Alignment(vertical="center")

        # Раскраска по приоритету
        hex_color, _ = PRIORITY_COLORS.get(a["priority"], ("DDDDDD", colors.grey))
        ws.cell(row=row, column=5).fill = PatternFill("solid", fgColor=hex_color)

        # SLA раскраска
        if a["sla_ok"]:
            ws.cell(row=row, column=7).fill = PatternFill("solid", fgColor="88CC88")
        else:
            ws.cell(row=row, column=7).fill = PatternFill("solid", fgColor="FF4444")
            ws.cell(row=row, column=7).font = Font(color="FFFFFF", bold=True)

    # Ширина колонок
    widths = [8, 10, 18, 16, 14, 50, 12]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # --- Лист 2: Загрузка инженеров ---
    ws2 = wb.create_sheet("Загрузка")

    ws2.merge_cells("A1:D1")
    ws2["A1"] = "Загрузка инженеров"
    ws2["A1"].font = Font(bold=True, size=14)
    ws2["A1"].alignment = Alignment(horizontal="center")

    eng_headers = ["ID инженера", "Слотов загружено", "Макс. слотов", "Утилизация %"]
    for col, h in enumerate(eng_headers, 1):
        cell = ws2.cell(row=3, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    loads = schedule_data.get("loads", {})
    for i, (eng_id, load) in enumerate(loads.items()):
        row = 4 + i
        max_slots = 8  # по умолчанию
        util = (load / max_slots * 100) if max_slots > 0 else 0
        for col, val in enumerate([eng_id, load, max_slots, f"{util:.0f}%"], 1):
            cell = ws2.cell(row=row, column=col, value=val)
            cell.border = border

    for i, w in enumerate([20, 18, 16, 16], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # --- Лист 3: Не назначенные ---
    unassigned = schedule_data.get("unassigned", [])
    if unassigned:
        ws3 = wb.create_sheet("Не назначенные")
        ws3.merge_cells("A1:B1")
        ws3["A1"] = "Заявки, не вошедшие в расписание"
        ws3["A1"].font = Font(bold=True, size=14)

        ws3["A3"] = "ID заявки"
        ws3["B3"] = "Причина"
        ws3["A3"].font = header_font
        ws3["A3"].fill = header_fill
        ws3["B3"].font = header_font
        ws3["B3"].fill = header_fill

        for i, tid in enumerate(unassigned):
            ws3.cell(row=4 + i, column=1, value=tid).border = border
            ws3.cell(row=4 + i, column=2, value="Недостаточно слотов или инженеров").border = border

        ws3.column_dimensions["A"].width = 20
        ws3.column_dimensions["B"].width = 40

    # Сохраняем в bytes
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_pdf(schedule_data: dict) -> bytes:
    """
    Экспортирует расписание в PDF.
    Возвращает bytes готового .pdf файла.

    schedule_data — ответ от /schedule эндпоинта оркестратора.
    """
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="RussianFont-Bold",
        fontSize=16,
        spaceAfter=10,
    )

    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontName="RussianFont",
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=6,
    )

    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="RussianFont-Bold",
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
    )

    elements = []

    # Заголовок
    elements.append(Paragraph("Расписание работ на день (MOLSP)", title_style))
    elements.append(Paragraph(
        f"Сформировано: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        f"Статус: {schedule_data.get('status', '?')} | "
        f"Штраф: {schedule_data.get('total_penalty', 0):.1f} | "
        f"Макс. загрузка: {schedule_data.get('max_load', 0)} слотов",
        meta_style,
    ))
    elements.append(Spacer(1, 10))

    # Таблица назначений
    elements.append(Paragraph("Назначения по слотам", section_style))

    assignments = schedule_data.get("assignments", [])
    sorted_a = sorted(assignments, key=lambda x: (x["slot"], x["engineer"]))

    table_data = [["Слот", "Инженер", "Заявка", "Приоритет", "Заголовок", "SLA"]]

    for a in sorted_a:
        sla_text = "OK" if a["sla_ok"] else "VIOLATION"
        table_data.append([
            f"Час {a['slot'] + 1}",
            a["engineer"],
            a["task_id"],
            a["priority"],
            a["title"][:50],
            sla_text,
        ])

    table = Table(table_data, colWidths=[50, 100, 80, 70, 220, 60])
    table_style = TableStyle([
        # Заголовок
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "RussianFont-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "RussianFont"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        # Тело
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F0F0")]),
    ])

    # Раскраска по приоритетам и SLA
    for i, a in enumerate(sorted_a, 1):
        _, pdf_color = PRIORITY_COLORS.get(a["priority"], ("DDDDDD", colors.grey))
        table_style.add("BACKGROUND", (3, i), (3, i), pdf_color)

        if not a["sla_ok"]:
            table_style.add("BACKGROUND", (5, i), (5, i), colors.red)
            table_style.add("TEXTCOLOR", (5, i), (5, i), colors.white)
            table_style.add("FONTNAME", (5, i), (5, i), "Helvetica-Bold")

    table.setStyle(table_style)
    elements.append(table)

    # Загрузка инженеров
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("Загрузка инженеров", section_style))

    loads = schedule_data.get("loads", {})
    load_data = [["Инженер", "Слотов", "Макс.", "Утилизация"]]
    for eng_id, load in loads.items():
        max_s = 8
        util = f"{(load / max_s * 100):.0f}%" if max_s > 0 else "0%"
        load_data.append([eng_id, str(load), str(max_s), util])

    load_table = Table(load_data, colWidths=[150, 80, 80, 100])
    load_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "RussianFont-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "RussianFont"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F0F0")]),
    ]))
    elements.append(load_table)

    # Не назначенные
    unassigned = schedule_data.get("unassigned", [])
    if unassigned:
        elements.append(Spacer(1, 15))
        elements.append(Paragraph("Не назначенные заявки", section_style))
        un_data = [["ID заявки", "Причина"]]
        for tid in unassigned:
            un_data.append([tid, "Недостаточно слотов или инженеров"])
        un_table = Table(un_data, colWidths=[150, 250])
        un_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF4444")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "RussianFont-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "RussianFont"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(un_table)

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()
