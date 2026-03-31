# Fase 2 — Descrição de Imagens com Gemini Vision

## Visão Geral

Este script é a **segunda etapa** do pipeline multimodal do projeto Agrônomo Virtual (SB100). Ele recebe as imagens extraídas de artigos científicos pela Fase 1 e utiliza a API do **Gemini 3.1 Pro** (Google) para gerar descrições textuais detalhadas de cada figura, gráfico, tabela ou foto encontrada.

O objetivo é transformar conteúdo visual — que não pode ser vetorizado diretamente — em texto rico e semanticamente relevante, para posterior vetorização e indexação no banco vetorial Qdrant (realizada pela Fase 3).

## Contexto no Pipeline

O pipeline completo é dividido em três códigos independentes que podem ser executados em dias e momentos diferentes:

| Etapa | O que faz | Dependências pesadas |
|-------|-----------|---------------------|
| **Código 1** — Extração | Converte PDFs em texto (Docling + OCR), gera chunks, vetoriza texto, extrai páginas com figuras e salva como PNG | Docling, Tesseract, Qwen3, OpenSearch Sparse |
| **Código 2** — Gemini *(este)* | Lê as imagens salvas, envia ao Gemini com contexto, recebe descrições estruturadas e atualiza o JSON de metadados | Apenas `requests` (leve) |
| **Código 3** — Vetorização de imagens | Lê as descrições do Gemini no JSON, vetoriza com Qwen3 + OpenSearch Sparse e faz upsert no Qdrant | Qwen3, OpenSearch Sparse |

A separação existe por motivos práticos: o Código 2 não carrega modelos de embedding (economia de RAM no Colab), e o Código 3 não consome créditos de API externa. Cada um pode ser re-executado independentemente sem retrabalho.

## Como Funciona

### Entrada

O script lê os arquivos `*-imagens-meta.json` gerados pela Fase 1, localizados em `data/Imagens/`. Cada JSON contém metadados bibliográficos do artigo e uma lista de páginas salvas como PNG, com o contexto textual extraído da região anterior à figura no documento.

Exemplo de entrada (JSON da Fase 1):

```json
{
  "arquivo_pdf": "Silva2020-adubacao-citros.pdf",
  "titulo": "Adubação nitrogenada em citros no estado de São Paulo",
  "autores": "Silva, J. A.; Souza, M. R.",
  "cultura": "Citricultura",
  "paginas": [
    {
      "arquivo_imagem": "Silva2020-adubacao-citros-pagina-005.png",
      "pagina_pdf": 5,
      "contexto_textual": "As doses de nitrogênio aplicadas variaram de 0 a 200 kg N ha-1...",
      "gemini_processado": false
    }
  ]
}
```

### Processamento

Para cada página com `"gemini_processado": false`, o script:

1. Carrega a imagem PNG e a codifica em base64.
2. Monta um prompt estruturado que inclui a imagem, o contexto textual da mesma região do PDF e os metadados bibliográficos do artigo (título, autores, cultura).
3. Envia para a API REST do Gemini 3.1 Pro Vision.
4. Recebe a resposta em JSON contendo, para cada figura detectada na página: o tipo (gráfico de linhas, barras, scatter, foto, diagrama, etc.), uma descrição detalhada de 2 a 4 frases, as variáveis e unidades identificadas, e uma conclusão principal.
5. Atualiza o JSON original com as descrições e marca `"gemini_processado": true`.

### Saída

O mesmo JSON é atualizado in-place com os campos de descrição:

```json
{
  "arquivo_imagem": "Silva2020-adubacao-citros-pagina-005.png",
  "pagina_pdf": 5,
  "contexto_textual": "As doses de nitrogênio aplicadas variaram de 0 a 200 kg N ha-1...",
  "gemini_processado": true,
  "gemini_data": "2026-03-31T14:22:01.123456",
  "figuras": [
    {
      "tipo": "grafico_linhas",
      "descricao": "Gráfico de linhas mostrando a resposta da produtividade de frutos de laranjeira Valência à adubação nitrogenada ao longo de 5 safras. O eixo X apresenta as doses de N (0, 50, 100, 150 e 200 kg ha-1) e o eixo Y a produtividade em t ha-1. Observa-se resposta crescente até 120 kg N ha-1, com estabilização nas doses superiores.",
      "variaveis": ["Dose de N (kg ha-1)", "Produtividade (t ha-1)"],
      "unidades": ["kg ha-1", "t ha-1"],
      "conclusao_principal": "A produtividade máxima foi atingida com aproximadamente 120 kg N ha-1, sem ganhos significativos em doses superiores."
    }
  ]
}
```

## Controle de Duplicatas

O campo `"gemini_processado"` garante idempotência. O script pode ser executado múltiplas vezes sem reprocessar imagens já descritas. Isso é importante porque:

- A Fase 1 pode ser executada em dias diferentes, gerando novos JSONs incrementalmente.
- Se a execução for interrompida (timeout, queda de conexão, limite de créditos), basta rodar novamente — apenas as páginas pendentes serão processadas.
- Erros são registrados no campo `"gemini_erro"` e a página é marcada como processada para evitar loops infinitos de tentativas.

## Prompt Engineering

O prompt enviado ao Gemini foi projetado para o domínio agrícola e inclui três fontes de informação complementares:

- **Imagem da página inteira**: o Gemini recebe a página completa do PDF renderizada como PNG, incluindo legendas, títulos de figuras, eixos e notas de rodapé. Isso evita os problemas de crops recortados que perdem contexto visual.
- **Contexto textual**: os últimos 800 caracteres de texto extraídos pela Fase 1 imediatamente antes da posição da figura no documento. Isso ajuda o Gemini a entender o que os dados representam.
- **Metadados bibliográficos**: título do artigo, autores e categoria/cultura. Isso orienta o Gemini para o domínio correto (ex: "citricultura" vs "cana-de-açúcar").

A temperatura é configurada em 0.1 para respostas determinísticas e factuais.

## Configuração

```python
GEMINI_API_KEY = "SUA_CHAVE_AQUI"       # API key do Google AI Studio
GEMINI_MODEL   = "gemini-3.1-pro-preview" # modelo com visão nativa
GEMINI_DELAY   = 5                        # segundos entre chamadas (rate limit)
```

A chave de API pode ser obtida em [Google AI Studio](https://aistudio.google.com/apikey). O delay entre chamadas deve ser ajustado conforme o tier da conta: ~5s para o tier gratuito, ~1-2s para contas pagas.

## Dependências

```bash
pip install requests
```

Este é o script mais leve do pipeline. Não carrega modelos de ML, não utiliza GPU e não acessa o Qdrant. A única dependência externa é a biblioteca `requests` para chamadas HTTP à API do Gemini.

## Execução

O script é projetado para rodar no **Google Colab**, com os arquivos armazenados no Google Drive:

```
Pdfextractor/
├── data/
│   ├── Imagens/
│   │   ├── artigo1-pagina-003.png
│   │   ├── artigo1-imagens-meta.json
│   │   ├── artigo2-pagina-007.png
│   │   ├── artigo2-imagens-meta.json
│   │   └── ...
```

Ao executar, o script exibe o progresso no console:

```
📁 Buscando JSONs em .../data/Imagens...
📄 45 JSONs encontrados.

============================================================
📄 Silva2020-adubacao-citros.pdf
  3 pendentes / 3 total
============================================================
  🔍 p.5 → Gemini... ✅ 2 figura(s)
    [1] grafico_linhas — Gráfico mostrando a resposta da produtividade de frutos de la...
    [2] grafico_barras — Comparação entre porta-enxertos quanto ao diâmetro do tronco...
  🔍 p.8 → Gemini... ✅ 1 figura(s)
    [1] foto — Fotografias de campo mostrando sintomas de deficiência de nitrogênio...
  🔍 p.12 → Gemini... 📭 nenhuma figura real
  💾 JSON atualizado: Silva2020-adubacao-citros-imagens-meta.json

🎉 Código 2 concluído!
  📷 Páginas processadas agora: 3
  ⏭️  Já processadas antes: 120
  🖼️  Figuras descritas: 3
  ❌ Erros: 0
```
