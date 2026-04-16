# ============================================================
# CÓDIGO 2 — Gemini Vision: descrever imagens
# ============================================================
# Lê os JSONs da fase 1, manda páginas pendentes para o Gemini,
# recebe descrições e atualiza o JSON.
#
# NÃO vetoriza, NÃO toca no Qdrant.
# Pode rodar várias vezes — nunca repete imagem já processada.
#
# INSTALAÇÕES:
# !pip install requests -q
# ============================================================

import os
import json
import base64
import time
from datetime import datetime
from pathlib import Path

import requests

# ============================================================
# CONFIGURAÇÕES
# ============================================================
GEMINI_API_KEY = ""  # ← colocar sua API key
GEMINI_MODEL   = "gemini-3.1-pro-preview"

# ── Google Drive
from google.colab import drive
drive.mount('/content/drive', force_remount=False)

BASE_DIR = Path("/content/drive/MyDrive/Pdfextractor")
IMG_DIR  = BASE_DIR / "data" / "Imagens"

# ── Rate limit (ajuste conforme seu tier)
GEMINI_DELAY = 5  # segundos entre chamadas

# ============================================================
# GEMINI VISION — chamada REST
# ============================================================
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

GEMINI_PROMPT_IMAGEM = """Você é um especialista em agronomia e ciências agrárias. Sua tarefa é extrair o MÁXIMO de informação quantitativa e qualitativa de cada figura presente nesta página de artigo científico.

Contexto textual extraído da mesma região do PDF:
\"\"\"{contexto}\"\"\"

Metadados do artigo:
- Título: {titulo}
- Autores: {autores}
- Cultura/Categoria: {cultura}

INSTRUÇÕES DETALHADAS:

Para GRÁFICOS (linhas, barras, scatter, pizza):
- Leia TODOS os valores dos eixos X e Y com suas unidades exatas
- Identifique CADA série/linha/barra pela legenda (ex: "Tratamento 1", "Variedade IAC-385")
- Extraia TODOS os pontos de dados visíveis com seus valores numéricos aproximados
- Identifique valores máximos, mínimos e pontos ótimos
- Descreva a tendência de cada série (crescente, decrescente, quadrática, estável)
- Se houver barras de erro ou letras de significância estatística, inclua
- Se houver equação de regressão (R², y=ax+b), transcreva

Para FOTOS:
- Descreva o que aparece com detalhes agronômicos (sintomas, estágio fenológico, parte da planta)
- Identifique tratamentos se houver comparação visual

Para DIAGRAMAS/MAPAS:
- Descreva a estrutura e as relações apresentadas
- Extraia valores numéricos se presentes

Para CADA figura encontrada na página, responda em JSON (lista):
[
  {{
    "tipo": "grafico_linhas|grafico_barras|grafico_pizza|scatter|tabela_imagem|foto|diagrama|mapa|outro",
    "titulo_figura": "Título ou legenda da figura como aparece no PDF (ex: Figura 3. Produtividade...)",
    "descricao": "Descrição detalhada de 4-8 frases. Inclua: o que o gráfico mostra, quais tratamentos/variáveis são comparados, qual a faixa de valores no eixo X e Y, e como os dados se comportam.",
    "variaveis": ["nome completo da variável X com unidade", "nome completo da variável Y com unidade"],
    "unidades": ["unidade X", "unidade Y"],
    "series_dados": ["nome da série 1 (legenda)", "nome da série 2"],
    "dados_extraidos": [
      {{"serie": "nome", "x": "valor_x", "y": "valor_y"}},
      {{"serie": "nome", "x": "valor_x", "y": "valor_y"}}
    ],
    "valor_maximo": "Descreva o ponto máximo observado com valores exatos (ex: produtividade máxima de 42.5 t/ha na dose de 120 kg N/ha)",
    "valor_minimo": "Descreva o ponto mínimo observado com valores exatos",
    "ponto_otimo": "Se identificável, descreva a dose/concentração/valor ótimo recomendado",
    "tendencia": "Descrição da tendência matemática (linear crescente, quadrática com pico em X, logarítmica, sem diferença significativa entre tratamentos, etc.)",
    "equacao_regressao": "Se visível no gráfico, transcreva a equação (ex: y = -0.002x² + 0.48x + 15.3, R² = 0.94)",
    "significancia_estatistica": "Se houver letras (a, b, c) ou asteriscos (* **) de significância, descreva quais tratamentos diferem",
    "conclusao_principal": "Conclusão prática em 1-2 frases que um agrônomo usaria para recomendar uma dose/prática"
  }}
]

Se a página NÃO contiver nenhuma figura real (só texto, logos ou decoração), responda:
[]

IMPORTANTE: Extraia valores numéricos EXATOS sempre que visíveis. É melhor um valor aproximado lido do gráfico do que nenhum valor.

Responda APENAS o JSON, sem markdown, sem ```."""


GEMINI_PROMPT_TABELA = """Você é um especialista em agronomia e ciências agrárias. Sua tarefa é extrair o MÁXIMO de informação quantitativa de cada tabela presente nesta página de artigo científico.

Contexto textual extraído da mesma região do PDF:
\"\"\"{contexto}\"\"\"

Texto markdown extraído da(s) tabela(s) pelo OCR (pode conter erros):
\"\"\"{tabelas_md}\"\"\"

Metadados do artigo:
- Título: {titulo}
- Autores: {autores}
- Cultura/Categoria: {cultura}

INSTRUÇÕES DETALHADAS:

- Identifique TODAS as colunas e suas unidades
- Identifique TODOS os tratamentos/linhas
- Extraia os valores numéricos mais importantes de cada célula
- Identifique qual tratamento teve o melhor e o pior resultado
- Se houver letras de significância estatística (a, b, c), descreva quais tratamentos diferem
- Se houver médias, desvios padrão ou coeficientes de variação, inclua
- Descreva relações dose-resposta se aplicável

Para CADA tabela encontrada na página, responda em JSON (lista):
[
  {{
    "tipo": "tabela",
    "titulo_figura": "Título da tabela como aparece no PDF (ex: Tabela 2. Teores foliares...)",
    "descricao": "Descrição detalhada de 5-8 frases. Inclua: quantas linhas e colunas, quais tratamentos são comparados, quais parâmetros são medidos, faixas de valores observados, e quais tratamentos se destacaram.",
    "variaveis": ["variável 1 (unidade)", "variável 2 (unidade)", "variável 3 (unidade)"],
    "unidades": ["unidade 1", "unidade 2", "unidade 3"],
    "series_dados": ["tratamento 1", "tratamento 2", "tratamento 3"],
    "dados_extraidos": [
      {{"tratamento": "nome", "parametro": "nome", "valor": "valor com unidade"}},
      {{"tratamento": "nome", "parametro": "nome", "valor": "valor com unidade"}}
    ],
    "valor_maximo": "Qual tratamento/parâmetro teve o maior valor e quanto foi",
    "valor_minimo": "Qual tratamento/parâmetro teve o menor valor e quanto foi",
    "ponto_otimo": "Se identificável, qual dose/tratamento/prática é a mais recomendada",
    "tendencia": "Descrição geral dos padrões nos dados",
    "equacao_regressao": "",
    "significancia_estatistica": "Quais tratamentos diferem estatisticamente entre si e em quais parâmetros",
    "conclusao_principal": "Conclusão prática em 1-2 frases que um agrônomo usaria para fazer uma recomendação"
  }}
]

Se a página NÃO contiver nenhuma tabela real, responda:
[]

IMPORTANTE: Extraia valores numéricos EXATOS. Use o markdown do OCR como referência mas confie mais na imagem visual da página.

Responda APENAS o JSON, sem markdown, sem ```."""


GEMINI_PROMPT_MISTO = """Você é um especialista em agronomia e ciências agrárias. Sua tarefa é extrair o MÁXIMO de informação quantitativa de cada figura e tabela presente nesta página.

Contexto textual extraído da mesma região do PDF:
\"\"\"{contexto}\"\"\"

Texto markdown extraído da(s) tabela(s) pelo OCR (pode conter erros):
\"\"\"{tabelas_md}\"\"\"

Metadados do artigo:
- Título: {titulo}
- Autores: {autores}
- Cultura/Categoria: {cultura}

INSTRUÇÕES:
- Para GRÁFICOS: leia todos os valores dos eixos, identifique cada série pela legenda, extraia pontos de dados, identifique máximos/mínimos/ótimos, transcreva equações de regressão se visíveis
- Para TABELAS: identifique todas colunas/linhas, extraia valores numéricos, compare tratamentos
- Para FOTOS: descreva com detalhes agronômicos

Para CADA elemento visual, responda em JSON (lista):
[
  {{
    "tipo": "grafico_linhas|grafico_barras|grafico_pizza|scatter|tabela|tabela_imagem|foto|diagrama|mapa|outro",
    "titulo_figura": "Título como aparece no PDF",
    "descricao": "Descrição detalhada de 4-8 frases com todos os valores numéricos visíveis",
    "variaveis": ["variável 1 (unidade)", "variável 2 (unidade)"],
    "unidades": ["unidade 1", "unidade 2"],
    "series_dados": ["série/tratamento 1", "série/tratamento 2"],
    "dados_extraidos": [
      {{"serie": "nome", "x": "valor_x", "y": "valor_y"}}
    ],
    "valor_maximo": "Ponto máximo com valores exatos",
    "valor_minimo": "Ponto mínimo com valores exatos",
    "ponto_otimo": "Dose/valor ótimo se identificável",
    "tendencia": "Tendência matemática observada",
    "equacao_regressao": "Equação se visível",
    "significancia_estatistica": "Diferenças estatísticas entre tratamentos",
    "conclusao_principal": "Conclusão prática para recomendação agronômica"
  }}
]

Se a página NÃO contiver nenhum conteúdo visual real, responda: []

Responda APENAS o JSON, sem markdown, sem ```."""


def chamar_gemini(img_path: str, contexto: str, titulo: str, autores: str,
                  cultura: str, tipo_conteudo: str = "imagem", tabelas_md: str = "") -> list:
    """Envia imagem + contexto para Gemini Vision. Retorna lista de figuras/tabelas."""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    # ── Escolher prompt conforme tipo de conteúdo
    if tipo_conteudo == "tabela":
        prompt_template = GEMINI_PROMPT_TABELA
    elif tipo_conteudo == "imagem+tabela":
        prompt_template = GEMINI_PROMPT_MISTO
    else:
        prompt_template = GEMINI_PROMPT_IMAGEM

    prompt = prompt_template.format(
        contexto=contexto[:1500],
        titulo=titulo,
        autores=autores,
        cultura=cultura,
        tabelas_md=tabelas_md[:2000] if tabelas_md else "(não disponível)",
    )

    body = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/png", "data": img_b64}},
                {"text": prompt}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
        }
    }

    resp = requests.post(GEMINI_URL, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        print(f"      ⚠️ Resposta inesperada: {data}")
        return []

    # Limpar markdown
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        figuras = json.loads(text)
        if not isinstance(figuras, list):
            figuras = [figuras]
        return figuras
    except json.JSONDecodeError:
        print(f"      ⚠️ JSON inválido: {text[:200]}...")
        return []


# ============================================================
# LOOP PRINCIPAL
# ============================================================
print(f"\n📁 Buscando JSONs em {IMG_DIR}...")
jsons = sorted(IMG_DIR.glob("*-imagens-meta.json"))
print(f"📄 {len(jsons)} JSONs encontrados.")

# ── Reparo automático: resetar páginas marcadas com erro 429
#    (erros de rate limit são temporários, devem ser reprocessados)
total_reparadas = 0
for json_path in jsons:
    with open(json_path, "r", encoding="utf-8") as f:
        meta_reparo = json.load(f)
    reparou = False
    for pag in meta_reparo.get("paginas", []):
        erro = pag.get("gemini_erro", "")
        if "429" in str(erro) or "Too Many Requests" in str(erro):
            pag.pop("gemini_processado", None)
            pag.pop("gemini_erro", None)
            pag.pop("gemini_data", None)
            pag.pop("figuras", None)
            reparou = True
            total_reparadas += 1
    if reparou:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta_reparo, f, ensure_ascii=False, indent=2)

if total_reparadas > 0:
    print(f"🔧 {total_reparadas} páginas reparadas (tinham erro 429 de execução anterior)")

total_processadas = 0
total_ja_feitas = 0
total_figuras = 0
total_erros = 0

for json_path in jsons:
    with open(json_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    arquivo_pdf = meta.get("arquivo_pdf", json_path.stem)
    titulo      = meta.get("titulo", "")
    autores     = meta.get("autores", "")
    cultura     = meta.get("cultura", "")
    paginas     = meta.get("paginas", [])

    pendentes = [p for p in paginas if not p.get("gemini_processado", False)]

    if not pendentes:
        total_ja_feitas += len(paginas)
        continue

    print(f"\n{'='*60}")
    print(f"📄 {arquivo_pdf}")
    print(f"  {len(pendentes)} pendentes / {len(paginas)} total")
    print(f"{'='*60}")

    json_modificado = False

    for pag in paginas:
        if pag.get("gemini_processado", False):
            continue

        img_filename = pag["arquivo_imagem"]
        img_path = IMG_DIR / img_filename
        page_no = pag.get("pagina_pdf", "?")
        contexto = pag.get("contexto_textual", "")
        tipo_conteudo = pag.get("tipo_conteudo", "imagem")
        tabelas_md = pag.get("tabelas_markdown", "")

        if not img_path.exists():
            print(f"  ⚠️ p.{page_no} — imagem não encontrada: {img_filename}")
            pag["gemini_processado"] = True
            pag["gemini_erro"] = "imagem não encontrada"
            pag["figuras"] = []
            json_modificado = True
            continue

        print(f"  🔍 p.{page_no} [{tipo_conteudo}] → Gemini...", end=" ", flush=True)

        try:
            figuras = chamar_gemini(
                str(img_path), contexto, titulo, autores, cultura,
                tipo_conteudo=tipo_conteudo, tabelas_md=tabelas_md
            )

            pag["gemini_processado"] = True
            pag["gemini_data"] = datetime.now().isoformat()
            pag["figuras"] = figuras
            json_modificado = True

            if not figuras:
                print(f"📭 nenhuma figura real")
            else:
                print(f"✅ {len(figuras)} figura(s)")
                for fig_idx, fig in enumerate(figuras):
                    print(f"    [{fig_idx+1}] {fig.get('tipo', '?')} — {fig.get('descricao', '')[:80]}...")
                total_figuras += len(figuras)

            total_processadas += 1

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                # Rate limit — NÃO marcar como processado (vai tentar de novo)
                print(f"⏳ Rate limit! Parando este PDF, continua na próxima execução.")
                # Salvar o que já processou deste PDF
                if json_modificado:
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)
                    print(f"  💾 JSON salvo (progresso parcial)")
                # Esperar mais tempo e pular para o próximo PDF
                print(f"  ⏳ Aguardando 60s antes de tentar próximo PDF...")
                time.sleep(60)
                break  # sai do loop de páginas deste PDF
            else:
                # Erro HTTP permanente (400, 500, etc) — marcar como processado
                print(f"❌ Erro HTTP: {e}")
                pag["gemini_processado"] = True
                pag["gemini_erro"] = str(e)
                pag["figuras"] = []
                json_modificado = True
                total_erros += 1

        except Exception as e:
            # Erro inesperado (rede, JSON, etc) — marcar como processado
            print(f"❌ Erro: {e}")
            pag["gemini_processado"] = True
            pag["gemini_erro"] = str(e)
            pag["figuras"] = []
            json_modificado = True
            total_erros += 1

        time.sleep(GEMINI_DELAY)

    # Salvar JSON atualizado
    if json_modificado:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"  💾 JSON atualizado: {json_path.name}")

# ============================================================
# RESUMO
# ============================================================
print(f"\n{'='*60}")
print(f"🎉 Código 2 concluído!")
print(f"  📷 Páginas processadas agora: {total_processadas}")
print(f"  ⏭️  Já processadas antes: {total_ja_feitas}")
print(f"  🖼️  Figuras descritas: {total_figuras}")
print(f"  ❌ Erros: {total_erros}")
print(f"{'='*60}")
