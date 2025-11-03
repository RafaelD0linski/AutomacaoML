from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import requests
import re
from typing import Optional
import logging
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Abridor de Produtos Mercado Livre")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


def extrair_mlb_id(url: str) -> Optional[str]:
    """
    Extrai o ID MLB de qualquer URL do Mercado Livre.
    """
    # Decodificar URL primeiro (para links com %2F, etc)
    url = unquote(url)
    
    # Padrões de regex
    padroes = [
        r'MLB-?(\d{8,12})',
        r'/p/MLB(\d{8,12})',
        r'items/MLB(\d{8,12})',
        r'MLB(\d{8,12})',
    ]
    
    for padrao in padroes:
        match = re.search(padrao, url, re.IGNORECASE)
        if match:
            mlb_id = f"MLB{match.group(1)}"
            logger.info(f"✅ ID extraído: {mlb_id}")
            return mlb_id
    
    logger.warning(f"❌ Nenhum ID encontrado")
    return None


def construir_url_produto(mlb_id: str) -> str:
    """
    Constrói a URL do produto diretamente do ID MLB.
    Não depende da API!
    """
    # Formato padrão das URLs do Mercado Livre
    # produto.mercadolivre.com.br/MLB-{id}-{slug-qualquer}
    # O slug não importa, o ID é suficiente!
    url = f"https://produto.mercadolivre.com.br/{mlb_id}-produto"
    logger.info(f"🔗 URL construída: {url}")
    return url


def verificar_produto_existe(mlb_id: str) -> bool:
    """
    Verifica se o produto existe fazendo uma requisição HEAD.
    Mais rápido e econômico que GET.
    """
    try:
        url = construir_url_produto(mlb_id)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9',
        }
        
        # HEAD é mais leve que GET
        response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        
        # Se retornar 200, produto existe
        # Se retornar 404, produto não existe
        existe = response.status_code == 200
        
        logger.info(f"{'✅' if existe else '❌'} Status: {response.status_code}")
        return existe
        
    except Exception as e:
        logger.error(f"Erro ao verificar produto: {e}")
        # Em caso de erro, assumir que existe e deixar o ML lidar
        return True


def resolver_link_real(link: str) -> str:
    """
    Resolve redirecionamentos de links encurtados.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        response = requests.get(link, allow_redirects=True, timeout=10, headers=headers)
        return response.url
        
    except:
        return link


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, erro: Optional[str] = None):
    """
    Página inicial com formulário.
    """
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "erro": erro}
    )


@app.post("/abrir")
async def abrir_produto(request: Request, link_produto: str = Form(...)):
    """
    Processa o link e redireciona para o produto.
    NOVA ABORDAGEM: Não usa API do ML!
    """
    
    link_produto = link_produto.strip()
    logger.info(f"\n{'='*60}")
    logger.info(f"📥 Link recebido: {link_produto}")
    
    if not link_produto:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "erro": "❌ Por favor, cole um link válido."}
        )
    
    # Extrair ID diretamente
    mlb_id = extrair_mlb_id(link_produto)
    
    # Se não encontrou, tentar resolver redirecionamentos
    if not mlb_id:
        logger.info("🔄 Tentando resolver redirecionamentos...")
        try:
            link_resolvido = resolver_link_real(link_produto)
            mlb_id = extrair_mlb_id(link_resolvido)
        except:
            pass
    
    if not mlb_id:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request, 
                "erro": "❌ Link inválido. Não foi possível identificar o código MLB do produto."
            }
        )
    
    # Construir URL diretamente (sem usar API!)
    url_produto = construir_url_produto(mlb_id)
    
    # Verificar se produto existe (opcional, mas recomendado)
    logger.info("🔍 Verificando se produto existe...")
    existe = verificar_produto_existe(mlb_id)
    
    if not existe:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request, 
                "erro": f"⚠️ Produto {mlb_id} não encontrado ou foi removido."
            }
        )
    
    # Redirecionar!
    logger.info(f"✅ Redirecionando para: {url_produto}")
    logger.info(f"{'='*60}\n")
    
    return RedirectResponse(url=url_produto, status_code=303)


@app.get("/testar/{mlb_id}")
async def testar_produto(mlb_id: str):
    """
    Endpoint de teste.
    """
    url = construir_url_produto(mlb_id)
    existe = verificar_produto_existe(mlb_id)
    
    return {
        "mlb_id": mlb_id,
        "url": url,
        "existe": existe,
        "mensagem": "Produto encontrado!" if existe else "Produto não encontrado"
    }


@app.get("/debug")
async def debug():
    """
    Teste rápido do sistema.
    """
    return {
        "status": "✅ Sistema funcionando!",
        "versao": "2.0 - Sem dependência da API",
        "info": "Agora construímos a URL diretamente do ID MLB",
        "teste": "Acesse /testar/MLB1234567890 para testar um produto"
    }


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 SERVIDOR MERCADO LIVRE - VERSÃO 2.0")
    print("="*60)
    print("✨ Nova versão SEM dependência da API")
    print("📍 Acesse: http://127.0.0.1:8000")
    print("🔍 Debug: http://127.0.0.1:8000/debug")
    print("="*60 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
