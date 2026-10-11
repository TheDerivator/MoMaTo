# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""Writing a table as CSV or XLSX into a spooled temporary file, so a big export never sits in
memory and the response can stream it (EXP-3, D-033).

CSV: UTF-8 with a byte order mark (Excel opens it right), comma separated, ISO dates, decimal
point. XLSX: one sheet, typed cells (numbers, dates), a frozen bold header row.
"""

import csv
import io
import tempfile
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import IO

import xlsxwriter

type Cell = str | int | float | Decimal | date | datetime | bool | None

BOM = "\ufeff"  # makes Excel read the file as UTF-8
CRLF = "\r\n"
CHUNK = 64 * 1024
SPOOL_LIMIT = 8 * 1024 * 1024  # in memory up to this size, then on disk


class ExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"

    @property
    def media_type(self) -> str:
        if self is ExportFormat.CSV:
            return "text/csv; charset=utf-8"
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _csv_text(value: Cell) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:.15g}"
    return str(value)


def write_csv(header: list[str], rows: Iterable[list[Cell]]) -> IO[bytes]:
    out: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=SPOOL_LIMIT)  # noqa: SIM115
    try:
        out.write(BOM.encode())
        text = io.TextIOWrapper(out, encoding="utf-8", newline="", write_through=True)
        writer = csv.writer(text, lineterminator=CRLF)
        writer.writerow(header)
        for row in rows:
            writer.writerow([_csv_text(cell) for cell in row])
        text.flush()
        text.detach()  # keep `out` open for the response
        out.seek(0)
    except BaseException:
        out.close()
        raise
    return out


def write_xlsx(header: list[str], rows: Iterable[list[Cell]], *, sheet: str) -> IO[bytes]:
    out: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=SPOOL_LIMIT)  # noqa: SIM115
    try:
        workbook = xlsxwriter.Workbook(out, {"constant_memory": True})
        try:
            bold = workbook.add_format({"bold": True})
            day = workbook.add_format({"num_format": "yyyy-mm-dd"})
            moment = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})
            sheet_ = workbook.add_worksheet(sheet[:31])
            sheet_.freeze_panes(1, 0)
            for column, title in enumerate(header):
                sheet_.set_column(column, column, min(max(len(title) + 2, 12), 40))
            sheet_.write_row(0, 0, header, bold)
            for index, row in enumerate(rows, start=1):
                for column, cell in enumerate(row):
                    if cell is None:
                        continue
                    if isinstance(cell, bool):
                        sheet_.write_boolean(index, column, cell)
                    elif isinstance(cell, datetime):
                        sheet_.write_datetime(index, column, cell.replace(tzinfo=None), moment)
                    elif isinstance(cell, date):
                        sheet_.write_datetime(
                            index, column, datetime.combine(cell, datetime.min.time()), day
                        )
                    elif isinstance(cell, int | float | Decimal):
                        sheet_.write_number(index, column, float(cell))
                    else:
                        sheet_.write_string(index, column, str(cell))
        finally:
            workbook.close()
        out.seek(0)
    except BaseException:
        out.close()
        raise
    return out


def write_table(
    kind: ExportFormat, header: list[str], rows: Iterable[list[Cell]], *, sheet: str
) -> IO[bytes]:
    if kind is ExportFormat.CSV:
        return write_csv(header, rows)
    return write_xlsx(header, rows, sheet=sheet)


def chunks(file: IO[bytes]) -> Iterator[bytes]:
    """The file's bytes in chunks; closes it when done (or when the client goes away)."""
    try:
        while block := file.read(CHUNK):
            yield block
    finally:
        file.close()
