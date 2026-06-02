"""
gutschein_pdf.py  —  IBK Bilderbuch Geschenkgutschein
=====================================================
Nutzt das Canva-PDF als Vorlage und befüllt:
  - Gutscheincode  (fett, gleiche Position wie Original)
  - Betrag in €    (CormorantGaramond wie GUTSCHEIN-Schrift, Bücher-Icon bleibt)

canva_gutschein.pdf muss neben dieser Datei liegen.
"""

import io, os, base64, logging
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

PAGE_H = 842.25
PAGE_W = 595.5

ROSA_BG      = HexColor("#F9EEF1")
BETRAG_X_RIGHT = 312.0
BETRAG_Y       = PAGE_H - 447.6
BETRAG_SIZE    = 36.0
BETRAG_COLOR   = HexColor("#2C2C2C")

COVER_BETRAG = (265.0, PAGE_H - 458.0, 312.0, PAGE_H - 412.0)

CODE_X    = 216.0
CODE_Y    = PAGE_H - 507.0
CODE_SIZE = 18.0
CODE_COLOR = HexColor("#1A1A1A")
COVER_CODE = (170.0, PAGE_H - 510.0, 400.0, PAGE_H - 486.0)


def _register_cormorant(template_path: str):
    """Extrahiert CormorantGaramond aus dem Canva-PDF und registriert es in ReportLab."""
    if 'CormorantGaramond' in pdfmetrics.getRegisteredFontNames():
        return
    try:
        reader = PdfReader(template_path)
        obj = reader.get_object(76)
        df  = obj['/DescendantFonts'].get_object()[0].get_object()
        fd  = df['/FontDescriptor'].get_object()
        font_data = fd['/FontFile2'].get_object().get_data()
        tmp = os.path.join(os.path.dirname(os.path.abspath(template_path)), '_cormorant_tmp.ttf')
        with open(tmp, 'wb') as f:
            f.write(font_data)
        pdfmetrics.registerFont(TTFont('CormorantGaramond', tmp))
        logger.info("CormorantGaramond registriert")
    except Exception as e:
        logger.warning(f"Cormorant-Font nicht ladbar, Fallback auf Helvetica: {e}")


def _make_overlay(code: str, betrag: float, use_cormorant: bool) -> bytes:
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))

    # Betrag-Platzhalter überdecken
    x0, y0, x1, y1 = COVER_BETRAG
    c.setFillColor(ROSA_BG)
    c.rect(x0, y0, x1-x0, y1-y0, fill=1, stroke=0)

    # Betrag einzeichnen
    c.setFillColor(BETRAG_COLOR)
    font = 'CormorantGaramond' if use_cormorant else 'Helvetica'
    c.setFont(font, BETRAG_SIZE)
    c.drawRightString(BETRAG_X_RIGHT, BETRAG_Y, f"{betrag:.0f}")

    # Code überdecken
    x0, y0, x1, y1 = COVER_CODE
    c.setFillColor(ROSA_BG)
    c.rect(x0, y0, x1-x0, y1-y0, fill=1, stroke=0)

    # Code einzeichnen
    c.setFillColor(CODE_COLOR)
    c.setFont("Helvetica-Bold", CODE_SIZE)
    c.drawString(CODE_X, CODE_Y, code)

    c.save()
    return buf.getvalue()


def generate_gutschein_pdf(
    code: str,
    betrag: float,
    template_path: str = None,
) -> bytes:
    base = os.path.dirname(os.path.abspath(__file__))
    tpl  = template_path or os.path.join(base, "canva_gutschein.pdf")

    if not os.path.exists(tpl):
        raise FileNotFoundError(f"Canva-Template nicht gefunden: {tpl}")

    _register_cormorant(tpl)
    use_cormorant = 'CormorantGaramond' in pdfmetrics.getRegisteredFontNames()

    reader = PdfReader(tpl)
    writer = PdfWriter()
    page   = reader.pages[0]

    overlay = PdfReader(io.BytesIO(_make_overlay(code, betrag, use_cormorant)))
    page.merge_page(overlay.pages[0])
    writer.add_page(page)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def send_gutschein_email(
    recipient: str,
    code: str,
    betrag: float,
    template_path: str = None,
    sendgrid_api_key: str = None,
    sender_email: str = None,
):
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import (
        Mail, Attachment, FileContent, FileName, FileType, Disposition
    )
    key    = sendgrid_api_key or os.getenv("SENDGRID_API_KEY")
    sender = sender_email     or os.getenv("EMAIL_SENDER")

    if not key or not sender:
        raise RuntimeError("SendGrid nicht konfiguriert")

    pdf_bytes = generate_gutschein_pdf(code, betrag, template_path)
    pdf_b64   = base64.b64encode(pdf_bytes).decode()

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;
                background:#FDFAF5;border-top:5px solid #7A9E7E;
                border-bottom:5px solid #9E4D6E;padding:36px;">
      <p style="font-size:9px;letter-spacing:3px;color:#1A1A1A;
                text-transform:uppercase;margin:0 0 3px;">I B K</p>
      <p style="font-size:9px;letter-spacing:1.5px;color:#9A9A9A;
                text-transform:uppercase;margin:0 0 24px;">
        Buchhandlung für Illustration und Bilderbücher</p>
      <h1 style="font-size:22px;font-weight:normal;color:#1A1A1A;margin:0 0 24px;">
        Geschenkgutschein</h1>
      <p style="color:#5A5A5A;font-size:14px;line-height:1.7;margin:0 0 24px;">
        Vielen Dank für deinen Kauf!<br>
        Im Anhang findest du deinen Gutschein als PDF zum Ausdrucken oder Weiterleiten.</p>
      <div style="background:#EDF3EE;border:1px solid #7A9E7E;border-radius:6px;
                  padding:14px;text-align:center;margin-bottom:20px;">
        <div style="font-size:10px;letter-spacing:2px;color:#7A9E7E;
                    text-transform:uppercase;margin-bottom:6px;">Wert</div>
        <div style="font-size:28px;font-weight:bold;color:#1A1A1A;">
          {betrag:.2f}&nbsp;€</div>
      </div>
      <p style="font-size:10px;letter-spacing:2px;color:#5A5A5A;
                text-transform:uppercase;text-align:center;margin:0 0 8px;">
        Dein Gutschein-Code</p>
      <div style="background:#F5ECF0;border:1px solid #9E4D6E;border-radius:6px;
                  padding:12px;text-align:center;font-family:monospace;
                  font-size:20px;letter-spacing:3px;color:#1A1A1A;
                  margin-bottom:24px;">{code}</div>
      <p style="color:#B0B0B0;font-size:10px;text-align:center;margin:0;">
        Einlösbar auf
        <a href="https://ibk-bilderbuch.de" style="color:#9E4D6E;">ibk-bilderbuch.de</a>
      </p>
    </div>
    """
    message = Mail(
        from_email=sender, to_emails=recipient,
        subject="Dein Geschenkgutschein von I B K",
        html_content=html_body,
    )
    message.attachment = Attachment(
        FileContent(pdf_b64), FileName("IBK-Geschenkgutschein.pdf"),
        FileType("application/pdf"), Disposition("attachment"),
    )
    SendGridAPIClient(key).send(message)
    logger.info("Gutschein gesendet an %s (Code %s)", recipient, code)
