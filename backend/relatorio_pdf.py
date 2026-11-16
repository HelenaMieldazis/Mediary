"""
Geração do relatório em PDF do Mediary.

Todo texto que veio do usuário (nome, descrições, texto da IA já revisado por ele)
passa por _p(): o reportlab interpreta marcação XML dentro de Paragraph, então o
texto precisa ser escapado, senão um "<" na descrição quebraria o PDF. Também
trocamos caracteres que a fonte padrão (Helvetica / WinAnsi) não consegue desenhar.
"""
import re
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ia_service import NOMES_TIPO, rotulo_sintoma

COR_MARCA = colors.HexColor("#173B5E")
COR_LINHA = colors.HexColor("#DDDDDD")
COR_ZEBRA = colors.HexColor("#F3F6FA")
LARGURA_UTIL = A4[0] - 3.6 * cm

_SUBSTITUICOES = {"→": "->", "←": "<-", "≥": ">=", "≤": "<=", "…": "...",
                  " ": " ", "​": "", "‑": "-"}


def sanitizar(texto):
    t = str(texto or "")
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    for a, b in _SUBSTITUICOES.items():
        t = t.replace(a, b)
    return t.encode("cp1252", errors="replace").decode("cp1252")


def _p(texto):
    """Texto seguro para Paragraph: sanitizado, escapado e com quebras de linha."""
    return escape(sanitizar(texto)).replace("\n", "<br/>")


def _br(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "-"


def _fmt_horas(h):
    if h is None:
        return "-"
    if h < 1:
        return f"{round(h * 60)} min"
    return f"{h:.1f}".replace(".", ",") + " h"


def _rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(1.8 * cm, 1 * cm, "Mediary - Relatório de Sintomas")
    canvas.drawRightString(A4[0] - 1.8 * cm, 1 * cm, f"Página {doc.page}")
    canvas.restoreState()


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("MTitulo", parent=base["Title"], textColor=COR_MARCA, spaceAfter=2),
        "subtitulo": ParagraphStyle("MSub", parent=base["Normal"], textColor=colors.HexColor("#555555"),
                                    fontSize=10, spaceAfter=10),
        "rotulo": ParagraphStyle("MRotulo", parent=base["Normal"], fontSize=10, leading=14),
        "secao": ParagraphStyle("MSecao", parent=base["Heading3"], textColor=COR_MARCA,
                                fontSize=12, spaceBefore=14, spaceAfter=6),
        "texto": ParagraphStyle("MTexto", parent=base["Normal"], fontSize=10, leading=14.5),
        "marcador": ParagraphStyle("MMarcador", parent=base["Normal"], fontSize=10, leading=14,
                                   leftIndent=14, firstLineIndent=-10, spaceAfter=3),
        "nota": ParagraphStyle("MNota", parent=base["Normal"], fontSize=8, leading=11,
                               textColor=colors.HexColor("#6B7280")),
        "celula": ParagraphStyle("MCelula", parent=base["Normal"], fontSize=8.5, leading=11),
        "rodape": ParagraphStyle("MRodape", parent=base["Normal"], fontSize=8, textColor=colors.grey),
    }


def _tabela(dados, larguras, zebra=True, centralizar_a_partir=None):
    t = Table(dados, colWidths=larguras, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_MARCA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, COR_LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if zebra:
        estilo.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COR_ZEBRA]))
    if centralizar_a_partir is not None:
        estilo.append(("ALIGN", (centralizar_a_partir, 0), (-1, -1), "CENTER"))
    t.setStyle(TableStyle(estilo))
    return t


def _secao_resumo_ia(ia, est):
    """Blocos que só existem no relatório com resumo por IA."""
    blocos = []

    blocos.append(Paragraph("Resumo do período", est["secao"]))
    blocos.append(Paragraph(_p(ia.get("resumo", "")), est["texto"]))
    blocos.append(Spacer(1, 4))
    blocos.append(Paragraph(
        "Resumo gerado com apoio de inteligência artificial a partir dos registros feitos pelo "
        "próprio paciente. Não é diagnóstico e não substitui a avaliação médica.", est["nota"]))

    destaques = [d for d in ia.get("destaques", []) if d]
    if destaques:
        blocos.append(Paragraph("Pontos observados", est["secao"]))
        for d in destaques:
            blocos.append(Paragraph("• " + _p(d), est["marcador"]))

    stats = ia.get("estatisticas") or {}
    if stats.get("total"):
        blocos.append(Paragraph("Panorama dos registros", est["secao"]))
        blocos.append(Paragraph(
            f"{stats['total']} registro(s) em {stats['dias_com_sintoma']} dia(s) diferente(s), "
            f"de {_br(stats['primeiro_registro'])} a {_br(stats['ultimo_registro'])}.", est["texto"]))
        blocos.append(Spacer(1, 6))

        linhas = [["Sintoma", "Registros", "Primeiro", "Último", "Duração média"]]
        for t in stats["por_tipo"]:
            linhas.append([Paragraph(_p(t["rotulo"]), est["celula"]), str(t["total"]),
                           _br(t["primeiro"]), _br(t["ultimo"]), _fmt_horas(t["duracao_media_horas"])])
        blocos.append(_tabela(linhas, [6.2 * cm, 2.2 * cm, 2.9 * cm, 2.9 * cm, 3.2 * cm],
                              centralizar_a_partir=1))
        blocos.append(Spacer(1, 8))

        abrev = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        dias = [["Dia da semana"] + abrev,
                ["Registros"] + [str(d["total"]) for d in stats["por_dia_semana"]]]
        blocos.append(_tabela(dias, [3.2 * cm] + [2.0 * cm] * 7, zebra=False, centralizar_a_partir=1))
        blocos.append(Spacer(1, 8))

        pers = [["Período do dia"] + [f"{p['periodo'].capitalize()}\n{p['faixa']}" for p in stats["por_periodo"]],
                ["Registros"] + [str(p["total"]) for p in stats["por_periodo"]]]
        pers[0] = [sanitizar(c) for c in pers[0]]
        blocos.append(_tabela(pers, [3.2 * cm] + [3.55 * cm] * 4, zebra=False, centralizar_a_partir=1))

        comb = stats.get("combinacoes_no_mesmo_dia") or []
        if comb:
            blocos.append(Spacer(1, 8))
            blocos.append(Paragraph("Sintomas registrados no mesmo dia (2 ou mais vezes):", est["texto"]))
            for c in comb:
                blocos.append(Paragraph(
                    f"• {_p(c['sintomas'][0])} + {_p(c['sintomas'][1])}: {c['dias']} dias", est["marcador"]))

        dur = stats.get("duracao")
        if dur:
            blocos.append(Spacer(1, 6))
            blocos.append(Paragraph(
                f"Duração (apenas registros com horário de término, {dur['com_termino']}): "
                f"média de {_fmt_horas(dur['media_horas'])}, máxima de {_fmt_horas(dur['maxima_horas'])}.",
                est["texto"]))

    perguntas = [q for q in ia.get("perguntas", []) if q]
    if perguntas:
        blocos.append(Paragraph("Perguntas para levar à consulta", est["secao"]))
        for q in perguntas:
            blocos.append(Paragraph("• " + _p(q), est["marcador"]))
    return blocos


def gerar_pdf_relatorio(usuario, sintomas, data_inicio=None, data_fim=None, ia=None):
    """PDF de um único paciente. 'ia' (opcional) = {resumo, destaques, perguntas, estatisticas}."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            title="Mediary - Relatório de Sintomas", author="Mediary")
    est = _estilos()

    el = [
        Paragraph("Mediary — Relatório de Sintomas", est["titulo"]),
        Paragraph("Documento gerado para acompanhamento médico", est["subtitulo"]),
        Paragraph(f"<b>Paciente:</b> {_p(usuario['nome'])}", est["rotulo"]),
        Paragraph(f"<b>E-mail:</b> {_p(usuario['email'])}", est["rotulo"]),
        Paragraph(f"<b>Gerado em:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", est["rotulo"]),
    ]
    if data_inicio or data_fim:
        periodo = f"{_br(data_inicio) if data_inicio else 'início do histórico'} até " \
                  f"{_br(data_fim) if data_fim else 'hoje'}"
        el.append(Paragraph(f"<b>Período:</b> {_p(periodo)}", est["rotulo"]))

    if ia:
        el += _secao_resumo_ia(ia, est)

    el.append(Paragraph("Registros detalhados" if ia else "Registros", est["secao"]))
    if not sintomas:
        el.append(Paragraph("Nenhum sintoma registrado no período selecionado.", est["texto"]))
    else:
        linhas = [["Início", "Fim", "Tipo", "Subtipo", "Descrição"]]
        for s in sintomas:
            ini = s["inicio"].strftime("%d/%m/%Y %H:%M") if s["inicio"] else "-"
            fim = s["fim"].strftime("%d/%m/%Y %H:%M") if s["fim"] else "-"
            tipo = NOMES_TIPO.get(s["tipo"]) or str(s["tipo"] or "-").replace("_", " ").capitalize()
            subtipo = str(s["subtipo"]).capitalize() if s["subtipo"] else "-"
            linhas.append([ini, fim, Paragraph(_p(tipo), est["celula"]),
                           Paragraph(_p(subtipo), est["celula"]),
                           Paragraph(_p(s["descricao"] or "-"), est["celula"])])
        el.append(_tabela(linhas, [2.8 * cm, 2.8 * cm, 2.6 * cm, 2.6 * cm, 5.4 * cm]))
        el.append(Spacer(1, 12))
        el.append(Paragraph(f"Total de registros: {len(sintomas)}", est["texto"]))

    el.append(Spacer(1, 24))
    el.append(Paragraph(
        "Este relatório foi gerado automaticamente pelo aplicativo Mediary a partir dos "
        "registros informados pelo próprio paciente e não substitui uma avaliação médica.",
        est["rodape"]))

    doc.build(el, onFirstPage=_rodape, onLaterPages=_rodape)
    buffer.seek(0)
    return buffer
