# pedagioSP
Agente de IA para consulta de pedágios do Estado de São Paulo

O arquivo é um agente de IA completo para pesquisa automática.
Buscar dados das URLs que fornecem informações sobre rodovias no Brasil e no Estado de São Paulo e analisa o custo da viagem.
Aqui está a análise detalhada e o resumo do que foi produzido:
________________________________________
Análise: Malha Rodoviária Paulista — Pedágios e Free-Flow (jun/2026)
Concessionárias e Tarifas (Categoria 1 — carro de passeio)
Concessionária	Grupo	Rodovias Principais	Tarifa 2026	Tipo
CCR AutoBAn	Motiva/CCR	SP-330 (Anhanguera) + SP-348 (Bandeirantes)	R$ 14,50/praça	Praça física
Ecovias Imigrantes	EcoRodovias	SP-150 (Anchieta) + SP-160 (Imigrantes)	R$ 40,50 (sistema completo)	Praça física
CCR ViaOeste	Motiva/CCR	SP-280 (Castello Branco metro) + SP-270	R$ 11,50/praça	Praça física
SPVias	Motiva/CCR	SP-280 interior + SP-270 médio	R$ 12,40/praça	Praça física
CART	Pátria	SP-270 (Raposo Tavares interior)	R$ 11,50/praça	Praça física
Intervias	Arteris/VINCI	SP-330 interior + SP-310	~R$ 11,00/praça	Praça física
Rota das Bandeiras	Comporte	SP-065 (Dom Pedro I)	R$ 14,50/praça	Praça física
Renovias / Colinas / Tietê	Arteris	SP-342, SP-310, SP-326...	~R$ 9,80-11,00/praça	Praça física
Free Flow Tamoios	Consórcio	SPI-097 / Contorno Sul	R$ 5,50/pórtico	FREE-FLOW ativo
Via Appia (Rodoanel Norte)	Via Appia	SP-021	variável	FREE-FLOW ativo
Ecovias Noroeste	EcoRodovias	SP-333 / SP-326	variável	FREE-FLOW ativo
Novo Litoral	Consórcio	SP-088/098/055	variável	FREE-FLOW ativo (nov/2025)
Motiva Sorocabana	CCR	8 rodovias / 460 km	R$ 11,50	Free-flow previsto jan/2027
Sistema Free-Flow — Como Funciona
•	Com TAG (Sem Parar, ConectCar etc.): desconto de até 20%, débito automático
•	Sem TAG: placa fotografada nos pórticos → 30 dias para pagar no Siga Fácil via PIX ou cartão
•	Não pagou? Multa de R$ 195,23 + 5 pontos na CNH
•	Cobrança proporcional ao trecho percorrido (não por praça fixa)
________________________________________
Como usar
# Instalar dependências
pip install anthropic httpx beautifulsoup4 rich

# Configurar API
export ANTHROPIC_API_KEY='sk-ant-...'   # Linux/Mac
$env:ANTHROPIC_API_KEY='sk-ant-...'     # Windows PowerShell

# Pergunta direta
python agente_pedagios_sp.py --query "Quanto custa ir de SP a Santos?"

# Modo interativo (recomendado)
python agente_pedagios_sp.py --interactive

# Demonstração com 5 perguntas padrão
python agente_pedagios_sp.py --demo --verbose


O que o agente faz
O agente usa Claude claude-sonnet-4-6 com tool use e 6 ferramentas especializadas:
Ferramenta	Função
buscar_concessionaria	Detalhes de qualquer concessionária (tarifas, praças, contato)
consultar_rota	Estima custo de pedágio entre duas cidades
listar_rodovias_free_flow	Lista todos os trechos free-flow ativos em 2026
verificar_pagamento_free_flow	Passo-a-passo para pagar via Siga Fácil
comparar_concessionarias	Tabela comparativa por tipo (física vs. free-flow)
buscar_informacoes_web	Busca web para dados mais recentes
________________________________________
Sources:
•	Free Flow – ANTT
•	Free Flow Tamoios
•	Siga Fácil SP
•	DER-SP – Valores de Pedágio
•	ARTESP – Portal de Dados Abertos
•	Motiva/CCR – Calcular Pedágio AutoBAn
•	Correiro da Manhã – Free flow adiado para 2027

Eng. Fernando do Couto
