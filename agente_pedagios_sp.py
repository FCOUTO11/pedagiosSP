"""
Agente de IA para Pesquisa de Pedágios do Estado de São Paulo
=============================================================
Usa o Claude claude-sonnet-4-6 com tool use para pesquisar, analisar e consultar
postos de pedágio físicos e pontos de cobrança automática (free-flow) em SP.

Requisitos:
    pip install anthropic httpx beautifulsoup4 rich

Uso:
    python agente_pedagios_sp.py
    python agente_pedagios_sp.py --query "Quanto custa de pedágio de SP a Campinas?"
    python agente_pedagios_sp.py --interactive
"""

import os
import re
import json
import argparse
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Any
import anthropic

# ---------------------------------------------------------------------------
# Base de conhecimento estruturada (análise detalhada das fontes)
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE = {
    "meta": {
        "fonte": "Análise consolidada de DER-SP, ARTESP, Siga Fácil, concessionárias e portais públicos",
        "atualizado": "2026-06",
        "nota": "Tarifas sujeitas a reajuste anual pela ARTESP. Verificar sempre as fontes oficiais."
    },

    "sistema_free_flow": {
        "descricao": (
            "O Free Flow é o sistema de cobrança automática sem cancelas instalado nas rodovias "
            "concedidas de SP. O veículo passa sem parar por pórticos eletrônicos que identificam "
            "a placa ou a tag. Com TAG: desconto de até 20% e débito automático. Sem TAG: 30 dias "
            "para pagar via Siga Fácil (sigafacil.sp.gov.br), PIX ou cartão. Não pagamento gera "
            "multa de R$ 195,23 + 5 pontos na CNH."
        ),
        "plataforma_pagamento": "https://www.sigafacil.sp.gov.br/",
        "prazo_pagamento_dias": 30,
        "multa_reais": 195.23,
        "pontos_cnh": 5,
        "rodovias_ativas_2026": [
            "Rodoanel Norte (SP-021) – Via Appia – Guarulhos",
            "Noroeste Paulista (SP-333/SP-326) – Ecovias Noroeste – Jaboticabal, Itápolis, Dobrada, Taiúva",
            "Rodovia dos Tamoios (SPI-097/055) – Free Flow Tamoios – Caraguatatuba (desde nov/2024)",
            "Raposo Tavares (SP-270) – Motiva Sorocabana – São Roque, Alumínio, Araçoiaba (trechos)",
            "Litoral Paulista (SP-088/098/055) – Novo Litoral (desde nov/2025)",
        ],
        "previsao_expansao": (
            "8 rodovias da Rota Sorocabana passam a operar free-flow a partir de jan/2027 "
            "(adiado pelo Gov. de SP em abr/2026)."
        ),
    },

    "concessionarias": [
        {
            "nome": "CCR AutoBAn (Motiva)",
            "grupo": "CCR / Motiva",
            "rodovias": ["SP-330 (Anhanguera)", "SP-348 (Bandeirantes)"],
            "extensao_km": 316,
            "tipo_cobranca": "Praça física + expansão free-flow prevista",
            "tarifa_cat1_2026": 14.50,
            "nota_tarifa": "Reajuste jul/2026 confirmado pela ARTESP",
            "pracas_principais": [
                {"local": "Perus", "km": 24, "rodovia": "SP-330", "sentido": "Interior"},
                {"local": "Cajamar", "km": 36, "rodovia": "SP-330", "sentido": "Interior"},
                {"local": "Jundiaí", "km": 58, "rodovia": "SP-330", "sentido": "Interior"},
                {"local": "Louveira", "km": 70, "rodovia": "SP-330", "sentido": "Interior"},
                {"local": "Valinhos", "km": 79, "rodovia": "SP-330", "sentido": "Interior"},
                {"local": "Campinas", "km": 94, "rodovia": "SP-330", "sentido": "Interior"},
                {"local": "Caieiras", "km": 31, "rodovia": "SP-348", "sentido": "Interior"},
                {"local": "Jundiaí", "km": 54, "rodovia": "SP-348", "sentido": "Interior"},
                {"local": "Louveira", "km": 68, "rodovia": "SP-348", "sentido": "Interior"},
                {"local": "Valinhos", "km": 81, "rodovia": "SP-348", "sentido": "Interior"},
                {"local": "Campinas", "km": 94, "rodovia": "SP-348", "sentido": "Interior"},
            ],
            "calcular_pedagio_url": "https://rodovias.motiva.com.br/autoban/servicos/calcular-pedagio/",
            "contato": "0800 055 4040",
        },
        {
            "nome": "Ecovias dos Imigrantes",
            "grupo": "EcoRodovias",
            "rodovias": ["SP-150 (Anchieta)", "SP-160 (Imigrantes)", "SP-040 (Imigrantes - acesso)"],
            "extensao_km": 177,
            "tipo_cobranca": "Praça física (sistema combinado: paga na ida OU na volta, nunca nos dois sentidos no mesmo dia)",
            "tarifa_cat1_2026": 40.50,
            "nota_tarifa": "Tarifa combinada para o sistema Anchieta-Imigrantes inteiro (ida+volta = R$ 40,50 pago uma vez)",
            "pracas_principais": [
                {"local": "Riacho Grande", "km": 28.8, "rodovia": "SP-150", "sentido": "Sul", "tarifa": 40.50},
                {"local": "Riacho Grande", "km": 28.5, "rodovia": "SP-150", "sentido": "Norte", "tarifa": 40.50},
                {"local": "Piratininga", "km": 29.0, "rodovia": "SP-160", "sentido": "Sul", "tarifa": 40.50},
                {"local": "Piratininga", "km": 29.0, "rodovia": "SP-160", "sentido": "Norte", "tarifa": 40.50},
            ],
            "calcular_pedagio_url": "https://www.ecovias.com.br/",
            "contato": "0800 197 0010",
        },
        {
            "nome": "CCR ViaOeste",
            "grupo": "CCR / Motiva",
            "rodovias": ["SP-280 (Castello Branco - trecho metro)", "SP-270 (Raposo Tavares - trecho metro)"],
            "extensao_km": 168,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 11.50,
            "nota_tarifa": "Valor por praça, sentido único",
            "pracas_principais": [
                {"local": "Osasco", "km": 19, "rodovia": "SP-280", "sentido": "Interior", "tarifa": 11.50},
                {"local": "Itapevi", "km": 32, "rodovia": "SP-280", "sentido": "Interior", "tarifa": 11.50},
                {"local": "Alumínio", "km": 82, "rodovia": "SP-270", "sentido": "Interior", "tarifa": 11.50},
            ],
            "calcular_pedagio_url": "https://rodovias.motiva.com.br/viaOeste/",
            "contato": "0800 055 3636",
        },
        {
            "nome": "SPVias (CCR / Motiva)",
            "grupo": "CCR / Motiva",
            "rodovias": ["SP-280 (Castello Branco - trecho interior)", "SP-270 (Raposo Tavares - trecho médio)"],
            "extensao_km": 297,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 12.40,
            "pracas_principais": [
                {"local": "Quadra", "km": 132, "rodovia": "SP-280", "sentido": "Oeste", "tarifa": 12.40},
                {"local": "Itatinga", "km": 182, "rodovia": "SP-280", "sentido": "Oeste", "tarifa": 12.40},
            ],
            "calcular_pedagio_url": "https://rodovias.motiva.com.br/spvias/servicos/calcular-pedagio/",
            "contato": "0800 017 3232",
        },
        {
            "nome": "CART (Concessionária Auto Raposo Tavares)",
            "grupo": "Pátria / Pátio",
            "rodovias": ["SP-270 (Raposo Tavares - trecho interior)"],
            "extensao_km": 382,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 11.50,
            "pracas_principais": [
                {"local": "Alumínio", "km": 82.5, "rodovia": "SP-270", "sentido": "Oeste", "tarifa": 11.50},
                {"local": "Itapetininga", "km": 163, "rodovia": "SP-270", "sentido": "Oeste", "tarifa": 11.50},
                {"local": "Ourinhos", "km": 348, "rodovia": "SP-270", "sentido": "Oeste", "tarifa": 11.50},
            ],
            "contato": "0800 707 6627",
        },
        {
            "nome": "Intervias",
            "grupo": "Arteris / VINCI",
            "rodovias": ["SP-330 (Anhanguera - trecho interior)", "SP-310 (Washington Luís - trecho)"],
            "extensao_km": 375,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 11.00,
            "nota_tarifa": "Valor aproximado por praça",
            "pracas_principais": [
                {"local": "Limeira", "km": 141, "rodovia": "SP-330", "sentido": "Norte", "tarifa": 11.00},
                {"local": "Araras", "km": 175, "rodovia": "SP-330", "sentido": "Norte", "tarifa": 11.00},
                {"local": "Leme", "km": 197, "rodovia": "SP-330", "sentido": "Norte", "tarifa": 11.00},
                {"local": "Pirassununga", "km": 217, "rodovia": "SP-330", "sentido": "Norte", "tarifa": 11.00},
            ],
            "contato": "0800 883 0300",
        },
        {
            "nome": "Rota das Bandeiras",
            "grupo": "Grupo Comporte / Engeform",
            "rodovias": ["SP-065 (Dom Pedro I)", "SP-332 (trecho)"],
            "extensao_km": 297,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 14.50,
            "contato": "0800 722 1717",
        },
        {
            "nome": "Renovias",
            "grupo": "Arteris / VINCI",
            "rodovias": ["SP-342 (Renovação)", "SP-334 (trecho)", "SP-350 (trecho)"],
            "extensao_km": 327,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 11.00,
            "contato": "0800 283 8000",
        },
        {
            "nome": "Rodovias das Colinas",
            "grupo": "Arteris / VINCI",
            "rodovias": ["SP-310 (Washington Luís - trecho norte)", "SP-326 (trecho)"],
            "extensao_km": 260,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 11.00,
            "contato": "0800 770 6633",
        },
        {
            "nome": "ViaRondon",
            "grupo": "Grupo OHL / Abertis",
            "rodovias": ["SP-300 (Marechal Rondon)"],
            "extensao_km": 526,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 9.80,
            "contato": "0800 016 7000",
        },
        {
            "nome": "Rodovias do Tietê",
            "grupo": "Arteris / VINCI",
            "rodovias": ["SP-310 (Washington Luís - trecho leste)", "SP-308 (trecho)"],
            "extensao_km": 415,
            "tipo_cobranca": "Praça física",
            "tarifa_cat1_2026": 9.80,
            "contato": "0800 702 3030",
        },
        {
            "nome": "Free Flow Tamoios",
            "grupo": "Consórcio Tamoios",
            "rodovias": ["SPI-097 (Tamoios - trecho planalto)", "SPI-055 (Contorno Sul)"],
            "extensao_km": 86,
            "tipo_cobranca": "FREE-FLOW (sem cancela)",
            "tarifa_cat1_2026": 5.50,
            "nota_tarifa": "Por pórtico no Contorno Sul km 13+500 (desde nov/2024). Moto: R$ 2,75",
            "porticos": [
                {"local": "Contorno Sul", "km": "13+500", "municipio": "Caraguatatuba"},
            ],
            "pagamento_url": "https://freeflowtamoios.com.br/",
            "contato": "0800 770 1055",
        },
        {
            "nome": "Via Appia (Rodoanel Norte)",
            "grupo": "Via Appia Concessões",
            "rodovias": ["SP-021 (Rodoanel Norte)"],
            "extensao_km": 44,
            "tipo_cobranca": "FREE-FLOW (sem cancela)",
            "tarifa_cat1_2026": None,
            "nota_tarifa": "Tarifa variável por pórtico e trecho. Consultar sigafacil.sp.gov.br",
            "municipios": ["Guarulhos", "São Paulo (zona norte)"],
            "pagamento_url": "https://www.sigafacil.sp.gov.br/",
        },
        {
            "nome": "Ecovias Noroeste Paulista",
            "grupo": "EcoRodovias",
            "rodovias": ["SP-333", "SP-326"],
            "extensao_km": 210,
            "tipo_cobranca": "FREE-FLOW (sem cancela)",
            "tarifa_cat1_2026": None,
            "nota_tarifa": "Tarifa por pórtico. Consultar sigafacil.sp.gov.br",
            "municipios": ["Jaboticabal", "Itápolis", "Dobrada", "Taiúva"],
            "pagamento_url": "https://www.sigafacil.sp.gov.br/",
        },
        {
            "nome": "Motiva Sorocabana (Rota Sorocabana)",
            "grupo": "CCR / Motiva",
            "rodovias": ["SP-270 (Raposo Tavares - trechos)", "SP-258 (João Mellão)", "outras SP"],
            "extensao_km": 460,
            "tipo_cobranca": "FREE-FLOW previsto jan/2027 (adiado em abr/2026)",
            "tarifa_cat1_2026": 11.50,
            "nota_tarifa": "Trechos em transição praça → free-flow",
            "pagamento_url": "https://rodovias.motiva.com.br/sorocabana/pedagio-eletronico/",
            "contato": "0800 070 7010",
        },
        {
            "nome": "Novo Litoral",
            "grupo": "Consórcio Novo Litoral",
            "rodovias": ["SP-088 (Pedro Eroles)", "SP-098 (Mogi-Bertioga)", "SP-055 (Rio-Santos - trecho norte)"],
            "extensao_km": 173,
            "tipo_cobranca": "FREE-FLOW (desde nov/2025)",
            "tarifa_cat1_2026": None,
            "nota_tarifa": "Tarifa por pórtico e trecho. Consultar sigafacil.sp.gov.br",
            "pagamento_url": "https://www.sigafacil.sp.gov.br/",
        },
    ],

    "rotas_comuns": {
        "sp_santos": {
            "descricao": "São Paulo → Santos (via Anchieta ou Imigrantes)",
            "concessionaria": "Ecovias dos Imigrantes",
            "rodovias": ["SP-150", "SP-160"],
            "tarifa_2026": 40.50,
            "nota": "Paga UMA vez no sistema combinado (ida+volta). Reveze entre Anchieta e Imigrantes conforme orientação da concessionária.",
        },
        "sp_campinas_anhanguera": {
            "descricao": "São Paulo → Campinas (via Anhanguera SP-330)",
            "concessionarias": ["CCR AutoBAn", "Intervias"],
            "custo_estimado_2026": 43.50,
            "nota": "~3 praças AutoBAn (até Campinas km 94) + praças Intervias após km 94",
        },
        "sp_campinas_bandeirantes": {
            "descricao": "São Paulo → Campinas (via Bandeirantes SP-348)",
            "concessionaria": "CCR AutoBAn",
            "custo_estimado_2026": 43.50,
            "nota": "~3 praças AutoBAn até Campinas",
        },
        "sp_sorocaba": {
            "descricao": "São Paulo → Sorocaba (via Castello Branco SP-280)",
            "concessionarias": ["CCR ViaOeste", "SPVias"],
            "custo_estimado_2026": 34.90,
            "nota": "2 praças ViaOeste + praças SPVias após km 79",
        },
        "sp_ribeirao_preto": {
            "descricao": "São Paulo → Ribeirão Preto (via Anhanguera SP-330)",
            "concessionarias": ["CCR AutoBAn", "Intervias"],
            "custo_estimado_2026": 87.00,
            "nota": "Estimativa: 5-6 praças no total ~316 km",
        },
        "sp_litoral_tamoios": {
            "descricao": "São Paulo → Caraguatatuba / Ubatuba (via Tamoios SPI-097)",
            "concessionarias": ["Free Flow Tamoios", "Novo Litoral"],
            "custo_estimado_2026": 5.50,
            "nota": "Free-flow no Contorno Sul. Pode haver pórticos adicionais.",
        },
        "sp_curitiba": {
            "descricao": "São Paulo → Curitiba (via Anchieta/Imigrantes + Régis Bittencourt BR-116)",
            "custo_estimado_2026": 80.0,
            "nota": "R$ 40,50 (Ecovias SP) + pedágios federais BR-116 (CCR RodoAnel/PRF). Valores estimados.",
        },
    },
}


# ---------------------------------------------------------------------------
# Ferramentas (tools) do agente
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "buscar_concessionaria",
        "description": (
            "Retorna informações completas sobre uma concessionária de rodovia de SP: "
            "rodovias, tarifas 2026, praças, tipo de cobrança (física ou free-flow) e contato."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {
                    "type": "string",
                    "description": "Nome ou parte do nome da concessionária (ex: 'Ecovias', 'AutoBAn', 'Tamoios')",
                },
            },
            "required": ["nome"],
        },
    },
    {
        "name": "consultar_rota",
        "description": (
            "Estima o custo total de pedágio entre dois pontos do Estado de SP, "
            "listando as concessionárias e rodovias no trajeto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origem": {"type": "string", "description": "Cidade ou ponto de partida (ex: 'São Paulo', 'Campinas')"},
                "destino": {"type": "string", "description": "Cidade ou destino (ex: 'Santos', 'Ribeirão Preto')"},
                "rodovia": {
                    "type": "string",
                    "description": "Rodovia preferencial (opcional, ex: 'SP-330', 'SP-150')",
                },
            },
            "required": ["origem", "destino"],
        },
    },
    {
        "name": "listar_rodovias_free_flow",
        "description": "Lista todas as rodovias com sistema de cobrança automática free-flow ativo em SP em 2026.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "buscar_informacoes_web",
        "description": (
            "Faz uma busca web para obter informações atualizadas sobre pedágios, tarifas ou "
            "concessionárias em SP. Use quando precisar de dados muito recentes não cobertos pela base."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta de busca (ex: 'tarifa Ecovias 2026 reajuste')",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "verificar_pagamento_free_flow",
        "description": (
            "Explica como verificar e pagar uma cobrança de pedágio free-flow pelo Siga Fácil "
            "e fornece o link correto da concessionária, dado uma placa ou rodovia."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rodovia": {"type": "string", "description": "Rodovia onde passou (ex: 'Tamoios', 'Rodoanel Norte')"},
                "placa": {"type": "string", "description": "Placa do veículo (opcional)"},
            },
            "required": ["rodovia"],
        },
    },
    {
        "name": "comparar_concessionarias",
        "description": "Compara tarifas e coberturas de múltiplas concessionárias em SP numa tabela resumida.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filtro_tipo": {
                    "type": "string",
                    "enum": ["todas", "free-flow", "fisica"],
                    "description": "Filtrar por tipo de cobrança: todas, free-flow ou física",
                },
            },
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Implementação das ferramentas
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def buscar_concessionaria(nome: str) -> dict:
    termo = _normalize(nome)
    resultados = []
    for c in KNOWLEDGE_BASE["concessionarias"]:
        if termo in _normalize(c["nome"]) or any(termo in _normalize(r) for r in c["rodovias"]):
            resultados.append(c)
    if not resultados:
        return {"erro": f"Nenhuma concessionária encontrada para '{nome}'. Tente: Ecovias, AutoBAn, ViaOeste, Tamoios, CART, Intervias, Colinas, Renovias, ViaRondon, Rota das Bandeiras."}
    return {"concessionarias": resultados}


def consultar_rota(origem: str, destino: str, rodovia: str | None = None) -> dict:
    rotas = KNOWLEDGE_BASE["rotas_comuns"]
    orig_n = _normalize(origem)
    dest_n = _normalize(destino)
    rod_n = _normalize(rodovia) if rodovia else ""

    # Busca direta nas rotas conhecidas
    for key, rota in rotas.items():
        desc_n = _normalize(rota["descricao"])
        if orig_n in desc_n and dest_n in desc_n:
            if rod_n and rod_n not in desc_n:
                continue
            return {"rota_encontrada": True, **rota}

    # Busca parcial: origem OU destino na descrição
    parciais = []
    for key, rota in rotas.items():
        desc_n = _normalize(rota["descricao"])
        if orig_n in desc_n or dest_n in desc_n:
            parciais.append(rota)

    if parciais:
        return {
            "rota_encontrada": False,
            "sugestoes": parciais,
            "aviso": f"Rota exata '{origem} → {destino}' não encontrada. Veja sugestões relacionadas.",
        }

    return {
        "rota_encontrada": False,
        "aviso": (
            f"Rota '{origem} → {destino}' não está mapeada na base. "
            "Para rotas complexas, consulte DER-SP WebRotas: "
            "https://www.der.sp.gov.br/WebSite/Servicos/ServicosOnline/WebRotas.aspx"
        ),
    }


def listar_rodovias_free_flow() -> dict:
    sistema = KNOWLEDGE_BASE["sistema_free_flow"]
    ff_conc = [c for c in KNOWLEDGE_BASE["concessionarias"] if "FREE-FLOW" in c.get("tipo_cobranca", "").upper()]
    return {
        "descricao_sistema": sistema["descricao"],
        "plataforma_pagamento": sistema["plataforma_pagamento"],
        "prazo_pagamento_dias": sistema["prazo_pagamento_dias"],
        "multa_reais": sistema["multa_reais"],
        "pontos_cnh_multa": sistema["pontos_cnh"],
        "rodovias_ativas_2026": sistema["rodovias_ativas_2026"],
        "previsao_expansao": sistema["previsao_expansao"],
        "concessionarias_free_flow": [
            {
                "nome": c["nome"],
                "rodovias": c["rodovias"],
                "tarifa_cat1": c.get("tarifa_cat1_2026"),
                "nota": c.get("nota_tarifa", ""),
                "pagamento_url": c.get("pagamento_url", ""),
            }
            for c in ff_conc
        ],
    }


def buscar_informacoes_web(query: str) -> dict:
    """Faz busca via DuckDuckGo Lite (sem autenticação)."""
    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; PedagiosAgente/1.0)"}
        resp = httpx.post(url, data={"q": query + " site:.gov.br OR site:.org.br OR site:.com.br"}, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for r in soup.select(".result__body")[:5]:
            title_el = r.select_one(".result__title")
            snippet_el = r.select_one(".result__snippet")
            link_el = r.select_one(".result__url")
            results.append({
                "titulo": title_el.get_text(strip=True) if title_el else "",
                "resumo": snippet_el.get_text(strip=True) if snippet_el else "",
                "url": link_el.get_text(strip=True) if link_el else "",
            })
        return {"query": query, "resultados": results, "fonte": "DuckDuckGo"}
    except Exception as e:
        return {"erro": str(e), "sugestao": f"Pesquise manualmente: https://duckduckgo.com/?q={query.replace(' ', '+')}"}


def verificar_pagamento_free_flow(rodovia: str, placa: str | None = None) -> dict:
    rod_n = _normalize(rodovia)
    concessionaria_info = None
    for c in KNOWLEDGE_BASE["concessionarias"]:
        if "FREE-FLOW" in c.get("tipo_cobranca", "").upper():
            if rod_n in _normalize(c["nome"]) or any(rod_n in _normalize(r) for r in c["rodovias"]):
                concessionaria_info = c
                break

    passo_a_passo = [
        "1. Acesse https://www.sigafacil.sp.gov.br/ (plataforma unificada do Gov. SP)",
        "2. Clique em 'Pague aqui'",
        "3. Digite a placa do veículo",
        "4. Selecione o débito correspondente à rodovia e data de passagem",
        "5. Pague via PIX ou cartão de crédito",
        "ATENÇÃO: Você tem 30 dias da passagem para pagar. Após esse prazo, incide multa de R$ 195,23 + 5 pontos na CNH.",
    ]

    resp: dict[str, Any] = {
        "rodovia_consultada": rodovia,
        "plataforma_pagamento_geral": "https://www.sigafacil.sp.gov.br/",
        "passo_a_passo": passo_a_passo,
    }
    if placa:
        resp["placa"] = placa.upper()
    if concessionaria_info:
        resp["concessionaria"] = concessionaria_info["nome"]
        resp["site_proprio"] = concessionaria_info.get("pagamento_url", "")
        resp["contato"] = concessionaria_info.get("contato", "")

    return resp


def comparar_concessionarias(filtro_tipo: str = "todas") -> dict:
    concs = KNOWLEDGE_BASE["concessionarias"]
    if filtro_tipo == "free-flow":
        concs = [c for c in concs if "FREE-FLOW" in c.get("tipo_cobranca", "").upper()]
    elif filtro_tipo == "fisica":
        concs = [c for c in concs if "FREE-FLOW" not in c.get("tipo_cobranca", "").upper()]

    tabela = []
    for c in concs:
        tabela.append({
            "concessionaria": c["nome"],
            "grupo": c.get("grupo", ""),
            "rodovias": ", ".join(c["rodovias"]),
            "tipo_cobranca": c.get("tipo_cobranca", ""),
            "tarifa_cat1_2026": c.get("tarifa_cat1_2026"),
            "extensao_km": c.get("extensao_km"),
        })
    return {"filtro": filtro_tipo, "total": len(tabela), "concessionarias": tabela}


# ---------------------------------------------------------------------------
# Dispatcher de ferramentas
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    "buscar_concessionaria": lambda inp: buscar_concessionaria(**inp),
    "consultar_rota": lambda inp: consultar_rota(**inp),
    "listar_rodovias_free_flow": lambda inp: listar_rodovias_free_flow(),
    "buscar_informacoes_web": lambda inp: buscar_informacoes_web(**inp),
    "verificar_pagamento_free_flow": lambda inp: verificar_pagamento_free_flow(**inp),
    "comparar_concessionarias": lambda inp: comparar_concessionarias(**inp),
}


def executar_ferramenta(nome: str, input_data: dict) -> str:
    handler = TOOL_HANDLERS.get(nome)
    if not handler:
        return json.dumps({"erro": f"Ferramenta '{nome}' não encontrada."})
    resultado = handler(input_data)
    return json.dumps(resultado, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Loop do agente
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""Você é um especialista em pedágios e malha rodoviária do Estado de São Paulo.

Sua base de conhecimento cobre (atualizada em junho/2026):
- 15+ concessionárias com rodovias, tarifas e tipo de cobrança (praça física ou free-flow)
- Sistema Free-Flow: funcionamento, pagamento via Siga Fácil, multas e prazos
- Rotas comuns entre cidades paulistas com estimativa de custo

Regras:
1. Sempre cite a tarifa atualizada e o tipo de cobrança (física vs. free-flow).
2. Informe ao usuário quando a tarifa pode variar (reajustes anuais pela ARTESP).
3. Para free-flow, sempre mencione o prazo de 30 dias e o Siga Fácil.
4. Se não tiver certeza, use a ferramenta 'buscar_informacoes_web'.
5. Responda em português brasileiro.
6. Para dúvidas sobre rotas não mapeadas, sugira o WebRotas do DER-SP.

Data de referência: {datetime.now().strftime('%d/%m/%Y')}
"""


def rodar_agente(pergunta: str, verbose: bool = False) -> str:
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": pergunta}]

    if verbose:
        print(f"\n[AGENTE] Processando: {pergunta}\n")

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Adiciona resposta do assistente ao histórico
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if verbose:
                        print(f"  → Ferramenta: {block.name}({json.dumps(block.input, ensure_ascii=False)})")
                    resultado = executar_ferramenta(block.name, block.input)
                    if verbose:
                        print(f"  ← Resultado: {resultado[:300]}...")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": resultado,
                    })
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            # Extrai o texto final
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "(sem resposta textual)"

        else:
            return f"[stop_reason inesperado: {response.stop_reason}]"


# ---------------------------------------------------------------------------
# Interface de linha de comando
# ---------------------------------------------------------------------------

PERGUNTAS_DEMO = [
    "Qual é a tarifa atual de pedágio para ir de São Paulo a Santos?",
    "Quais rodovias de SP já têm sistema free-flow ativo em 2026?",
    "Como pago um pedágio free-flow da Rodovia dos Tamoios se não tenho tag?",
    "Compare as tarifas de todas as concessionárias físicas de SP.",
    "Quanto custa de pedágio de São Paulo a Campinas pela Anhanguera?",
]


def modo_interativo() -> None:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()
    console.print(Panel.fit(
        "[bold blue]Agente de Pedágios SP[/bold blue]\n"
        "Pesquisa automática de postos físicos e free-flow\n"
        "[dim]Digite 'sair' para encerrar | 'demo' para exemplos[/dim]",
        border_style="blue",
    ))

    while True:
        try:
            pergunta = console.input("\n[bold green]Você:[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not pergunta:
            continue
        if pergunta.lower() == "sair":
            break
        if pergunta.lower() == "demo":
            for i, p in enumerate(PERGUNTAS_DEMO, 1):
                console.print(f"  {i}. {p}")
            continue

        with console.status("[yellow]Consultando agente...[/yellow]"):
            resposta = rodar_agente(pergunta, verbose=False)

        console.print("\n[bold cyan]Agente:[/bold cyan]")
        console.print(Markdown(resposta))


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente IA - Pedágios do Estado de São Paulo")
    parser.add_argument("--query", "-q", type=str, help="Pergunta direta ao agente")
    parser.add_argument("--interactive", "-i", action="store_true", help="Modo interativo (requer 'rich')")
    parser.add_argument("--demo", "-d", action="store_true", help="Executa perguntas de demonstração")
    parser.add_argument("--verbose", "-v", action="store_true", help="Exibe chamadas de ferramentas")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  Defina a variável de ambiente ANTHROPIC_API_KEY antes de usar o agente.")
        print("   export ANTHROPIC_API_KEY='sk-ant-...'")
        return

    if args.interactive:
        modo_interativo()
    elif args.demo:
        for pergunta in PERGUNTAS_DEMO:
            print(f"\n{'='*70}")
            print(f"PERGUNTA: {pergunta}")
            print("-" * 70)
            resposta = rodar_agente(pergunta, verbose=args.verbose)
            print(f"RESPOSTA:\n{resposta}")
    elif args.query:
        resposta = rodar_agente(args.query, verbose=args.verbose)
        print(resposta)
    else:
        # Pergunta padrão de demonstração
        pergunta = "Quais rodovias de SP têm pedágio free-flow em 2026 e como funciona o pagamento?"
        print(f"Pergunta: {pergunta}\n")
        resposta = rodar_agente(pergunta, verbose=True)
        print(f"\nResposta:\n{resposta}")


if __name__ == "__main__":
    main()
