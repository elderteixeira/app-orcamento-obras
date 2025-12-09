import pandas as pd
import sqlite3
import os

DB_PATH = 'orcamento_obras.db'
ARQUIVO_EXCEL = 'base_pesquisa.xlsx'

def limpar_texto(texto):
    """Remove tabulações, quebras de linha e espaços extras."""
    if pd.isna(texto): return ""
    s = str(texto).replace('\t', ' ').replace('\n', ' ').strip()
    if s == '#N/D' or s == '#REF!':
        return ""
    return s

def tratar_numero_hibrido(valor):
    """
    Corrige o bug da 'Explosão de Valores'.
    Lida tanto com formato PT-BR (1.000,00) quanto US/Excel (1000.00)
    """
    if pd.isna(valor): return 0.0
    
    # Transforma em string para analisar
    s = str(valor).replace('R$', '').strip()
    
    # Lógica de decisão:
    if ',' in s:
        # Se tem vírgula, é formato Brasileiro (ex: 1.250,50 ou 99,18)
        s = s.replace('.', '')  # Remove ponto de milhar
        s = s.replace(',', '.') # Transforma vírgula em ponto decimal
    else:
        # Se NÃO tem vírgula, assume que é formato padrão do Excel/Python (ex: 99.18)
        # Nesse caso, não removemos o ponto, pois ele JÁ É o decimal.
        pass 
        
    try:
        return float(s)
    except:
        return 0.0

def importar_dados(conn):
    print("--- 1/2 Processando aba 'item' ---")
    
    # Importante: dtype=str mantém os códigos (001) e força a leitura crua
    df_itens = pd.read_excel(ARQUIVO_EXCEL, sheet_name='item', dtype=str, engine='openpyxl')
    
    # Renomeando colunas (Caso você já tenha ajustado o Excel para snake_case)
    # Se ainda não ajustou o Excel, o script tentará achar as colunas
    # Mapeamento de segurança:
    col_map = {
        'código': 'codigo', 'descrição': 'descricao', 'custo': 'custo_ref', 
        'classificacao insumo': 'classificacao', 'classificação': 'classificacao'
    }
    df_itens.columns = df_itens.columns.str.lower().str.strip()
    df_itens = df_itens.rename(columns=col_map)
    
    # Limpeza
    df_itens['descricao'] = df_itens['descricao'].apply(limpar_texto)
    df_itens['tipo'] = df_itens['tipo'].apply(limpar_texto)
    df_itens['unidade'] = df_itens['unidade'].apply(limpar_texto)
    
    if 'classificacao' in df_itens.columns:
        df_itens['classificacao'] = df_itens['classificacao'].apply(limpar_texto)
    
    # AQUI ESTA A CORREÇÃO DO VALOR
    df_itens['custo_ref'] = df_itens['custo_ref'].apply(tratar_numero_hibrido)
    
    # Salva
    cols_banco = ['codigo', 'descricao', 'tipo', 'unidade', 'custo_ref', 'classificacao']
    cols_finais = [c for c in cols_banco if c in df_itens.columns]
    
    df_itens = df_itens.dropna(subset=['codigo'])
    df_itens[cols_finais].to_sql('insumos', conn, if_exists='replace', index=False)
    print(f"   -> {len(df_itens)} itens importados para tabela 'insumos'.")

    print("--- 2/2 Processando aba 'analiticas' ---")
    
    df_ana = pd.read_excel(ARQUIVO_EXCEL, sheet_name='analiticas', dtype=str, engine='openpyxl')
    
    # Normaliza colunas
    df_ana.columns = df_ana.columns.str.lower().str.strip()
    col_map_ana = {
        'código da composição': 'codigo_pai', 'código do item': 'codigo_filho', 
        'coeficiente': 'quantidade'
    }
    df_ana = df_ana.rename(columns=col_map_ana)
    
    # Limpeza
    df_ana['codigo_pai'] = df_ana['codigo_pai'].apply(limpar_texto)
    df_ana['codigo_filho'] = df_ana['codigo_filho'].apply(limpar_texto)
    
    # CORREÇÃO TAMBÉM NO COEFICIENTE (caso tenha algum texto formatado)
    df_ana['quantidade'] = df_ana['quantidade'].apply(tratar_numero_hibrido)
    
    df_ana = df_ana[df_ana['quantidade'] > 0]
    
    df_ana.to_sql('composicoes', conn, if_exists='replace', index=False)
    print(f"   -> {len(df_ana)} vínculos importados para tabela 'composicoes'.")

def main():
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("Banco de dados antigo excluído.")
        except:
            print("AVISO: Não consegui apagar o DB antigo.")

    conn = sqlite3.connect(DB_PATH)
    try:
        importar_dados(conn)
        print("\n--- SUCESSO TOTAL! Base importada e corrigida. ---")
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()