from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import requests
import re
from typing import Optional
import logging

# Configurar logging para debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Abridor de Produtos Mercado Livre")

# Configurar templates e arquivos estáticos
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


def extrair_mlb_id(url: str) -> Optional[str]:
    """
    Extrai o ID MLB de qualquer URL do Mercado Livre.
    Suporta múltiplos formatos de URL.
    """
    # Tentar diferentes padrões de regex
    padroes = [
        r'MLB-?(\d{8,12})',  # MLB1234567890 ou MLB-1234567890
        r'/p/MLB(\d{8,12})',  # mercadolivre.com.br/p/MLB123456
        r'items/MLB(\d{8,12})',  # API URLs
        r'MLB(\d{8,12})',  # Qualquer MLB seguido de números
    ]
    
    for padrao in padroes:
        match = re.search(padrao, url, re.IGNORECASE)
        if match:
            mlb_id = f"MLB{match.group(1)}"
            logger.info(f"ID extraído: {mlb_id} usando padrão: {padrao}")
            return mlb_id
    
    logger.warning(f"Nenhum ID encontrado na URL: {url}")
    return None


def resolver_link_real(link: str) -> str:
    """
    Resolve redirecionamentos e retorna a URL final.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        logger.info(f"Resolvendo link: {link}")
        response = requests.get(
            link,
            allow_redirects=True,
            timeout=15,
            headers=headers
        )
        
        url_final = response.url
        logger.info(f"URL resolvida: {url_final}")
        return url_final
        
    except requests.RequestException as e:
        logger.error(f"Erro ao resolver link: {e}")
        return link


def obter_permalink_produto(mlb_id: str) -> Optional[dict]:
    """
    Consulta a API oficial do Mercado Livre.
    Retorna um dict com 'permalink' e 'title' ou None.
    """
    try:
        # Endpoint da API do Mercado Livre
        api_url = f"https://api.mercadolibre.com/items/{mlb_id}"
        logger.info(f"Consultando API: {api_url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json'
        }
        
        response = requests.get(api_url, timeout=10, headers=headers)
        logger.info(f"Status da API: {response.status_code}")
        
        if response.status_code == 200:
            dados = response.json()
            permalink = dados.get('permalink')
            title = dados.get('title', 'Produto')
            
            logger.info(f"Produto encontrado: {title}")
            logger.info(f"Permalink: {permalink}")
            
            return {
                'permalink': permalink,
                'title': title,
                'id': mlb_id
            }
            
        elif response.status_code == 404:
            logger.warning(f"Produto {mlb_id} não encontrado (404)")
            return None
            
        else:
            logger.error(f"Erro na API: Status {response.status_code}")
            logger.error(f"Resposta: {response.text[:200]}")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Erro ao consultar API: {e}")
        return None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, erro: Optional[str] = None):
    """
    Rota principal que exibe o formulário HTML.
    """
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "erro": erro}
    )


@app.post("/abrir")
async def abrir_produto(request: Request, link_produto: str = Form(...)):
    """
    Rota que processa o link do produto e redireciona para a página real.
    """
    
    # Limpar o link
    link_produto = link_produto.strip()
    logger.info(f"\n{'='*60}")
    logger.info(f"Nova requisição recebida")
    logger.info(f"Link original: {link_produto}")
    
    if not link_produto:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "erro": "❌ Por favor, cole um link válido."}
        )
    
    # Tentar extrair ID diretamente do link fornecido primeiro
    mlb_id = extrair_mlb_id(link_produto)
    
    # Se não encontrou, tentar resolver redirecionamentos
    if not mlb_id:
        logger.info("ID não encontrado no link original, resolvendo redirecionamentos...")
        try:
            link_resolvido = resolver_link_real(link_produto)
            mlb_id = extrair_mlb_id(link_resolvido)
        except Exception as e:
            logger.error(f"Erro ao resolver redirecionamentos: {e}")
    
    # Se ainda não encontrou o ID
    if not mlb_id:
        logger.error("Falha ao extrair ID MLB")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request, 
                "erro": "❌ Link inválido. Não foi possível identificar o código do produto (MLB)."
            }
        )
    
    # Consultar API do Mercado Livre
    logger.info(f"Consultando produto {mlb_id} na API...")
    resultado = obter_permalink_produto(mlb_id)
    
    if not resultado or not resultado.get('permalink'):
        logger.error(f"Produto {mlb_id} não encontrado na API")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request, 
                "erro": f"⚠️ Produto {mlb_id} não encontrado ou indisponível."
            }
        )
    
    # Sucesso! Redirecionar para o produto
    permalink = resultado['permalink']
    logger.info(f"✅ Redirecionando para: {permalink}")
    logger.info(f"{'='*60}\n")
    
    return RedirectResponse(url=permalink, status_code=303)


@app.get("/testar/{mlb_id}")
async def testar_produto(mlb_id: str):
    """
    Endpoint de teste para verificar se um produto existe.
    Acesse: http://127.0.0.1:8000/testar/MLB19444510
    """
    resultado = obter_permalink_produto(mlb_id)
    
    if resultado:
        return {
            "sucesso": True,
            "produto": resultado
        }
    else:
        return {
            "sucesso": False,
            "mensagem": f"Produto {mlb_id} não encontrado"
        }


@app.get("/debug")
async def debug_info():
    """
    Endpoint para verificar se a aplicação está funcionando.
    Acesse: http://127.0.0.1:8000/debug
    """
    # Testar alguns produtos conhecidos
    produtos_teste = ["MLB3826970145", "MLB1000", "MLB19444510"]
    resultados = []
    
    for mlb_id in produtos_teste:
        resultado = obter_permalink_produto(mlb_id)
        resultados.append({
            "id": mlb_id,
            "existe": resultado is not None,
            "dados": resultado if resultado else "Não encontrado"
        })
    
    return {
        "status": "ok",
        "mensagem": "Aplicação funcionando",
        "testes": resultados
    }


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Iniciando servidor...")
    print("📍 Acesse: http://127.0.0.1:8000")
    print("🔍 Debug: http://127.0.0.1:8000/debug")
    print("🧪 Testar produto: http://127.0.0.1:8000/testar/MLB3826970145\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
