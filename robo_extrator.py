from playwright.sync_api import sync_playwright
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
import streamlit as st

def extrair_planilha_legado():
    print("Iniciando robo de extracao em segundo plano...")
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True) 
        pagina = navegador.new_page()
        
        pagina.goto("https://alrs.cloud4biz.com/4biz/webmvc/login")

        usuario_4Biz = st.secrets["USUARIO_SISTEMA"]
        senha_4Biz = st.secrets["SENHA_SISTEMA"]
        
        pagina.fill("input[name='user_login']", usuario_4Biz)
        pagina.wait_for_timeout(2000)
        pagina.click("input[name='password']")
        pagina.locator("input[name='password']").press_sequentially(senha_4Biz, delay=100)
        pagina.wait_for_timeout(1000)
        pagina.click("button[type='button']")

        pagina.click("input[name='password']")
        pagina.locator("input[name='password']").press_sequentially(senha_4Biz, delay=100)
        pagina.wait_for_timeout(1000)
        pagina.click("button[type='button']")

        print("Aguardando o processamento do login...")
        pagina.wait_for_timeout(10000)

        print("Indo para a tela de relatorios...")
        pagina.goto(
            "https://alrs.cloud4biz.com/4biz/pages/smartDecisions/smartDecisions.load#/smart-decisions/fd69368c-6c5f-42a6-8ddd-0d9044feb7c7",
            timeout=90000
        )

        print("Aguardando o botao do menu 'relatorio'...")
        botao_relatorio = pagina.locator("a[title='relatório']")
        botao_relatorio.wait_for(state="visible", timeout=15000)
        botao_relatorio.click()
        
        pagina.wait_for_timeout(30000)
        
        print("Abrindo os filtros do relatorio no Iframe...")
        frame_dashboard = pagina.frame_locator("iframe").first
        botao_filtros = frame_dashboard.locator("a[ng-click='mostrarFiltros(true)']")
        botao_filtros.wait_for(state="attached", timeout=30000)
        botao_filtros.click(force=True)
        
        pagina.wait_for_timeout(3000)
        
        print("Aguardando o clique no botao de gerar CSV...")
        with pagina.expect_download(timeout=60000) as download_info:
            frame_dashboard.locator("button[ng-click='gerarCSV()']").click(force=True)
            
        download = download_info.value
        
        # Ajuste do nome do arquivo salvo
        caminho_arquivo = os.path.join(os.getcwd(), "chamados4Biz.csv")
        download.save_as(caminho_arquivo)
        print(f"Download concluido: {caminho_arquivo}")
        
        navegador.close()
        return caminho_arquivo

def atualizar_banco_dados(caminho_arquivo):
    print("Iniciando processamento de dados e UPSERT...")
    
    try:
        df = pd.read_csv(caminho_arquivo, sep=';', encoding='utf-8', skiprows=2)
        df.columns = df.columns.str.strip()
        
        df['Data Abertura'] = pd.to_datetime(df['Data Abertura'], format='%d/%m/%Y %H:%M', errors='coerce')
        df['Data Solução'] = pd.to_datetime(df['Data Solução'], format='%d/%m/%Y %H:%M', errors='coerce')

        antes = len(df)
        df = df.dropna(subset=['Data Abertura'])
        depois = len(df)
        
        if antes != depois:
            print(f"Aviso: {antes - depois} linhas descartadas por falta de Data de Abertura.")

        df = df.astype(object).where(pd.notnull(df), None)

        db_url = st.secrets["NEON_DB_URL"]
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        query_upsert = """
            INSERT INTO chamados (
                ticket, situacao_tarefa, tipo_demanda, origem, descricao, 
                data_abertura, data_solucao, grupo, resolvedor, solicitante, 
                lotacao, solucao_resposta
            )
            VALUES %s
            ON CONFLICT (ticket) 
            DO UPDATE SET
                situacao_tarefa = EXCLUDED.situacao_tarefa,
                tipo_demanda = EXCLUDED.tipo_demanda,
                origem = EXCLUDED.origem,
                descricao = EXCLUDED.descricao,
                data_abertura = EXCLUDED.data_abertura,
                data_solucao = EXCLUDED.data_solucao,
                grupo = EXCLUDED.grupo,
                resolvedor = EXCLUDED.resolvedor,
                solicitante = EXCLUDED.solicitante,
                lotacao = EXCLUDED.lotacao,
                solucao_resposta = EXCLUDED.solucao_resposta;
        """

        valores_para_inserir = [
            (
                str(linha['Ticket']), 
                linha['Situação da Tarefa'],
                linha['Tipo Demanda'],
                linha['Origem Solicitação'],
                linha['Descrição'],
                linha['Data Abertura'],
                linha['Data Solução'],
                linha['Grupo'],
                linha['Resolvedor'],
                linha['Solicitante'],
                linha['Lotação'],
                linha['Solução Resposta']
            )
            for index, linha in df.iterrows()
        ]

        print(f"Sincronizando {len(valores_para_inserir)} chamados no NeonDB...")
        execute_values(cursor, query_upsert, valores_para_inserir)
        
        conn.commit()
        print("Banco de dados atualizado com sucesso!")

    except Exception as e:
        print(f"Erro no processamento ou banco de dados: {e}")
        if 'conn' in locals(): conn.rollback()
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    arquivo = extrair_planilha_legado()
    if arquivo:
        atualizar_banco_dados(arquivo)