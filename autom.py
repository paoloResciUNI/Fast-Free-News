import requests
from bs4 import BeautifulSoup
from transformers import pipeline
import os
from datetime import datetime
import time
from urllib.robotparser import RobotFileParser
import re

# Configurazione
HUGO_CONTENT_DIR = "content/posts/"
SCRAPER_DELAY = 30  # secondi tra le richieste

# Inizializza il modello di summarization
print("Caricamento modello di summarization...")
summarizer = pipeline(
    "summarization", 
    model="facebook/bart-large-cnn",
    tokenizer="facebook/bart-large-cnn"
)
print("Modello caricato!")

def check_robots_txt(url):
    """Verifica il file robots.txt del sito"""
    try:
        base_url = f"{url.scheme}://{url.netloc}"
        rp = RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        rp.read()
        return rp.can_fetch("*", url.geturl())
    except:
        return True  # Se non riesci a leggere robots.txt, procedi con cautela

def sanitize_filename(title):
    """Crea un filename sicuro dal titolo"""
    safe_title = re.sub(r'[^a-zA-Z0-9èéàùìò\s]', '', title)
    safe_title = re.sub(r'\s+', '_', safe_title.strip())
    return safe_title[:50]  # Limita la lunghezza

def scrape_article(url):
    """Scraping rispettoso degli articoli"""
    try:
        # Controlla robots.txt
        if not check_robots_txt(url):
            print(f"Robots.txt vieta scraping per: {url}")
            return None
        
        headers = {
            'User-Agent': 'AcademicResearchScraper/1.0 (+https://example.com)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'it,en;q=0.5'
        }
        
        response = requests.get(url.geturl(), headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Rimuovi elementi non desiderati
        for element in soup(['script', 'style', 'nav', 'footer', 'aside']):
            element.decompose()
        
        # Estrazione contenuto (adattabile per diversi siti)
        title_elem = soup.find('h1') or soup.find('title')
        title = title_elem.get_text().strip() if title_elem else "Titolo non disponibile"
        
        # Gestione speciale per arXiv
        if 'arxiv.org' in url.netloc:
            # Per arXiv, cerca il titolo specifico
            title_h1 = soup.find('h1', class_='title')
            if title_h1:
                title = title_h1.get_text().replace('Title:', '').strip()
            
            # Cerca l'abstract
            abstract_div = soup.find('blockquote', class_='abstract')
            if abstract_div:
                abstract_text = abstract_div.get_text().replace('Abstract:', '').strip()
                content = abstract_text
            else:
                content = ""
        else:
            # Estrai il contenuto principale - strategie multiple
            content = ""
            
            # Prova a trovare il contenuto principale
            main_content = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'content|main|body'))
            
            if main_content:
                paragraphs = main_content.find_all('p')
                content = ' '.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
            else:
                # Fallback: tutti i paragrafi
                paragraphs = soup.find_all('p')
                content = ' '.join([p.get_text().strip() for p in paragraphs[:10]])
        
        return {
            'title': title,
            'content': content[:5000],  # Limita per il modello
            'url': url.geturl(),
            'scraped_date': datetime.now().isoformat(),
            'source_domain': url.netloc
        }
        
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
        return None

def generate_summary(text, title):
    """Genera riassunto con modello locale"""
    try:
        if len(text) < 100:
            return "Contenuto troppo breve per generare un riassunto significativo."
        
        # Prepara il testo per il modello
        input_text = f"{title}. {text}" if title else text
        
        # Genera il riassunto
        input_length = len(input_text[:1024].split())
        max_len = min(150, max(50, input_length // 2))  # Adatta max_length dinamicamente
        
        summary = summarizer(
            input_text[:1024],  # Limita input per il modello
            max_length=max_len,
            min_length=min(50, max_len // 2),
            do_sample=False,
            truncation=True
        )
        
        return summary[0]['summary_text']
        
    except Exception as e:
        print(f"Errore generazione summary: {e}")
        return "Riassunto non disponibile"

def create_hugo_post(article_data):
    """Crea file Markdown per Hugo"""
    try:
        # Frontmatter per Hugo
        metadata = {
            'title': article_data['title'],
            'date': datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z'),
            'publishDate': datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z'),
            'source_url': article_data['url'],
            'source_domain': article_data['source_domain'],
            'categories': ['scienza', 'ricerca', article_data['source_domain']],
            'tags': ['open-access', 'scienza'],
            'summary': article_data['summary'][:200] + '...' if len(article_data['summary']) > 200 else article_data['summary'],
            'draft': False
        }
        
        # Crea directory se non esiste
        os.makedirs(HUGO_CONTENT_DIR, exist_ok=True)
        
        # Crea filename
        safe_title = sanitize_filename(article_data['title'])
        filename = f"{HUGO_CONTENT_DIR}{safe_title}.md"
        
        # Crea il contenuto del post
        post_content = f"""---
title: "{metadata['title']}"
date: {metadata['date']}
publishDate: {metadata['publishDate']}
source_url: "{metadata['source_url']}"
source_domain: "{metadata['source_domain']}"
categories: {metadata['categories']}
tags: {metadata['tags']}
summary: "{metadata['summary']}"
draft: {str(metadata['draft']).lower()}
---

{article_data['summary']}

---

**Fonte:** [{metadata['source_domain']}]({metadata['source_url']})
"""
        
        # Scrivi il file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(post_content)
        
        print(f"Creato: {filename}")
        
    except Exception as e:
        print(f"Errore creazione post: {e}")

def get_arxiv_articles():
    """Esempio: recupera articoli recenti da arXiv"""
    try:
        arxiv_url = "https://arxiv.org/list/cs.AI/recent"
        response = requests.get(arxiv_url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        articles = []
        for dt in soup.find_all('dt'):
            link = dt.find('a', href=re.compile(r'/abs/'))
            if link and 'href' in link.attrs:
                article_id = link['href'].split('/')[-1]
                full_url = f"https://arxiv.org/abs/{article_id}"
                articles.append(full_url)
        
        return articles[:3]  # Limita a 3 articoli per test
        
    except Exception as e:
        print(f"Errore recupero arXiv: {e}")
        return []

def main():
    """Funzione principale"""
    print("Avvio scraping articoli scientifici...")
    
    # Raccolta URL da vari sorgenti
    article_urls = []
    
    # Aggiungi sorgenti qui
    article_urls.extend(get_arxiv_articles())
    
    # Esempi aggiuntivi (sostituisci con le tue fonti)
    sample_urls = [
        "https://arxiv.org/abs/2305.10403",  # Esempio arXiv
        # Aggiungi altre URL qui
    ]
    article_urls.extend(sample_urls)
    
    print(f"Trovati {len(article_urls)} articoli da processare")
    
    for i, url_str in enumerate(article_urls):
        try:
            print(f"\nProcessing ({i+1}/{len(article_urls)}): {url_str}")
            
            url = requests.utils.urlparse(url_str)
            if not all([url.scheme, url.netloc]):
                print("URL non valida")
                continue
            
            article = scrape_article(url)
            if article and article['content']:
                print(f"Generando riassunto per: {article['title']}")
                article['summary'] = generate_summary(article['content'], article['title'])
                create_hugo_post(article)
            else:
                print("Nessun contenuto trovato o scraping fallito")
            
            # Rispetta il delay tra le richieste
            if i < len(article_urls) - 1:
                time.sleep(SCRAPER_DELAY)
                
        except Exception as e:
            print(f"Errore processing URL {url_str}: {e}")
            continue

if __name__ == "__main__":
    main()