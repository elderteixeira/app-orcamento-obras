import streamlit as st
import pandas as pd
import sqlite3

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Orçamento de Obras PRO", layout="wide", page_icon="🏗️")

# --- ESTADO DA SESSÃO ---
if 'orcamento' not in st.session_state:
    st.session_state['orcamento'] = []

# --- CONEXÃO ---
@st.cache_resource
def get_connection():
    return sqlite3.connect("orcamento_obras.db", check_same_thread=False)

# --- NOVA BUSCA ULTRA-AVANÇADA (PADRÃO PDF/EXCEL) ---
def buscar_avancada(texto_contem, texto_nao_contem, ordenar_por="Custo Crescente"):
    conn = get_connection()
    
    # Base da Query
    sql = "SELECT codigo, descricao, unidade, custo_ref, tipo FROM insumos WHERE 1=1"
    params = []

    # 1. TRATAMENTO "CONTÉM" (Lógica E)
    # Separador por espaço, conforme regra do PDF 
    if texto_contem:
        # Substitui curingas do usuário (?, *) pelos do SQL (_, %) 
        termos_sim = texto_contem.replace('*', '%').replace('?', '_').split()
        for termo in termos_sim:
            sql += " AND (LOWER(descricao) LIKE ? OR codigo = ?)"
            t_like = f"%{termo.lower()}%"
            params.extend([t_like, termo])

    # 2. TRATAMENTO "NÃO CONTÉM" (Lógica NÃO) 
    if texto_nao_contem:
        termos_nao = texto_nao_contem.replace('*', '%').replace('?', '_').split()
        for termo in termos_nao:
            sql += " AND LOWER(descricao) NOT LIKE ?"
            params.append(f"%{termo.lower()}%")

    # 3. ORDENAÇÃO 
    if ordenar_por == "Custo Crescente":
        sql += " ORDER BY custo_ref ASC"
    elif ordenar_por == "Custo Decrescente":
        sql += " ORDER BY custo_ref DESC"
    else: # Descrição
        sql += " ORDER BY descricao ASC"

    sql += " LIMIT 100"
    
    return pd.read_sql(sql, conn, params=params)

def pegar_composicao(codigo_pai):
    conn = get_connection()
    query = """
        SELECT 
            c.codigo_filho, i.descricao, i.unidade, c.quantidade, i.custo_ref
        FROM composicoes c
        LEFT JOIN insumos i ON c.codigo_filho = i.codigo
        WHERE c.codigo_pai = ?
    """
    return pd.read_sql(query, conn, params=(codigo_pai,))

# --- FUNÇÃO AUXILIAR DE ADIÇÃO ---
def adicionar_item_memoria(codigo, descricao, unidade, tipo, qtd, preco_unit, bdi):
    novo_item = {
        "Item": str(len(st.session_state['orcamento']) + 1), # Numeração sequencial simples
        "Código": codigo,
        "Descrição": descricao,
        "Tipo": tipo,
        "Unidade": unidade,
        "Qtd": float(qtd),
        "Preço Unit.": float(preco_unit),
        "BDI (%)": float(bdi),
        "Total": float(qtd) * float(preco_unit) * (1 + bdi/100)
    }
    st.session_state['orcamento'].append(novo_item)

# --- JANELA FLUTUANTE (DIALOG) ---
@st.dialog("Pesquisa SINAPI", width="large")
def modal_pesquisa(bdi_atual):
    st.markdown("Use espaços para separar palavras. Use `?` para 1 caractere ou `*` para vários. ")
    
    # Layout igual ao do PDF 
    col1, col2 = st.columns(2)
    with col1:
        contem = st.text_input("Contêm", placeholder="Ex: alvenaria 9 ceramic", key="search_contem")
    with col2:
        nao_contem = st.text_input("Não contêm", placeholder="Ex: betoneira", key="search_nao")
    
    col_ordem, col_resumo = st.columns([1, 2])
    with col_ordem:
        # Opções de ordenação do PDF 
        ordem = st.selectbox("Classificar por", ["Custo Crescente", "Custo Decrescente", "Descrição"])
    
    # Dispara a busca se houver texto
    if contem:
        df = buscar_avancada(contem, nao_contem, ordem)
        
        if not df.empty:
            st.caption(f"{len(df)} itens encontrados.")
            
            # Tabela selecionável
            event = st.dataframe(
                df,
                column_config={
                    "custo_ref": st.column_config.NumberColumn("Custo", format="R$ %.2f"),
                },
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun" # Isso faz o app rodar assim que clica
            )
            
            # Lógica de Seleção
            if len(event.selection.rows) > 0:
                idx = event.selection.rows[0]
                item_escolhido = df.iloc[idx]
                
                # Verifica se é composição para somar preço
                df_filhos = pegar_composicao(item_escolhido['codigo'])
                if not df_filhos.empty:
                    custo_real = (df_filhos['quantidade'] * df_filhos['custo_ref']).sum()
                    tipo = "Composição"
                else:
                    custo_real = item_escolhido['custo_ref']
                    tipo = "Insumo"

                # ADICIONA AO ORÇAMENTO
                adicionar_item_memoria(
                    codigo=item_escolhido['codigo'],
                    descricao=item_escolhido['descricao'],
                    unidade=item_escolhido['unidade'],
                    tipo=tipo,
                    qtd=1.0,
                    preco_unit=custo_real,
                    bdi=bdi_atual
                )
                st.success(f"Item {item_escolhido['codigo']} adicionado!")
                st.rerun() # Fecha o modal e atualiza a tela de fundo
                
        else:
            st.warning("Nenhum item encontrado na base.")
            st.markdown("---")
            st.info("Item não encontrado? Feche esta janela para digitar manualmente na planilha.")

# --- TELA PRINCIPAL ---
st.title("🏗️ Orçamento de Obras")

# Controles Superiores
c_bdi, c_botao = st.columns([1, 4])
with c_bdi:
    bdi_padrao = st.number_input("BDI Geral (%)", value=25.0)
with c_botao:
    st.write("") # Espaço para alinhar
    st.write("")
    # ESSE BOTÃO ABRE A JANELA FLUTUANTE
    if st.button("🔍 Pesquisar / Adicionar Item (F2)", type="primary", use_container_width=True):
        modal_pesquisa(bdi_padrao)

st.markdown("---")

# --- GRID (PLANILHA) ---
if len(st.session_state['orcamento']) > 0:
    df_orcamento = pd.DataFrame(st.session_state['orcamento'])
    
    # Data Editor
    df_editado = st.data_editor(
        df_orcamento,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Item": st.column_config.TextColumn("Item"),
            "Total": st.column_config.NumberColumn("Total", format="R$ %.2f", disabled=True),
            "Preço Unit.": st.column_config.NumberColumn("Unitário", format="%.2f"),
            "Qtd": st.column_config.NumberColumn("Qtd", format="%.2f"),
        },
        key="editor_principal"
    )

    # Recálculo
    df_editado['Total'] = df_editado['Qtd'] * df_editado['Preço Unit.'] * (1 + df_editado['BDI (%)']/100)
    st.session_state['orcamento'] = df_editado.to_dict('records')
    
    # Totalizadores
    total = df_editado['Total'].sum()
    st.markdown(f"### 💰 Total Global: R$ {total:,.2f}")

else:
    st.info("A planilha está vazia. Clique em 'Pesquisar' acima ou adicione uma linha manual abaixo.")
    # Inicia tabela vazia editável para inserção manual direta
    df_vazio = pd.DataFrame(columns=["Item", "Código", "Descrição", "Tipo", "Unidade", "Qtd", "Preço Unit.", "BDI (%)", "Total"])
    df_manual = st.data_editor(df_vazio, num_rows="dynamic", key="editor_vazio")
    
    if not df_manual.empty:
         # Se o usuário digitou algo na tabela vazia, salva na memória
         st.session_state['orcamento'] = df_manual.to_dict('records')
         st.rerun()