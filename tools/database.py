import streamlit as st
import psycopg2
from langchain.tools import tool

@tool
def consultar_banco_neondb(query_sql: str) -> str:
    """
    Acione esta ferramenta para executar consultas SQL no banco de dados Postgres.
    Use esta ferramenta APENAS para buscar informações na tabela 'chamados'.
    O parâmetro 'query_sql' deve ser uma string contendo APENAS o comando SQL válido.
    """
    try:
        # Puxa a string de conexão segura do nosso cofre local
        db_url = st.secrets["NEON_DB_URL"]
        
        # Abre a conexão com o NeonDB
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Executa a query gerada pelo LLM (Groq)
        cursor.execute(query_sql)
        
        # Verifica se é uma consulta de leitura
        if query_sql.strip().upper().startswith("SELECT"):
            resultados = cursor.fetchall()
            
            # Captura o nome das colunas para a IA saber o que é cada dado
            nomes_colunas = [desc[0] for desc in cursor.description]
            
            # Monta um dicionário limpo para a IA ler facilmente
            dados_formatados = [dict(zip(nomes_colunas, linha)) for linha in resultados]
            retorno = str(dados_formatados)
        else:
            conn.commit()
            retorno = "Comando executado com sucesso."
            
        # Fecha as portas
        cursor.close()
        conn.close()
        
        return retorno

    except Exception as e:
        return f"Erro ao executar a query SQL: {str(e)}. Corrija a sintaxe da query e tente novamente."