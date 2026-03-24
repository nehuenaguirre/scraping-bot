
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re
import time
import random
import os

URL_BASE = os.getenv("RENDER_EXTERNAL_URL", "http://127.0.0.1:5000")

API_PRODUCTOS = f"{URL_BASE}/api/productos"
API_BAJAS = f"{URL_BASE}/api/productos/bajas"
API_URLS = f"{URL_BASE}/api/urls_objetivo"

def limpiar_precio(texto_precio):
    if not texto_precio: return 0.0
    texto = str(texto_precio).replace(',', '')
    coincidencias = re.findall(r'[0-9\.]+', texto)
    if coincidencias:
        try: return float(coincidencias[0])
        except ValueError: return 0.0
    return 0.0

def limpiar_stock(texto_stock):
    if not texto_stock or "agotado" in texto_stock.lower(): return 0
    numeros = re.findall(r'\d+', texto_stock)
    return int(numeros[0]) if numeros else 0

def extraer_categorias_dinamicas(url_origen):
    partes = [p for p in url_origen.strip('/').split('/') if p]
    categoria = "General"
    subcategoria = "" 
    
    if 'product-category' in partes:
        idx = partes.index('product-category')
        carpetas = partes[idx + 1:] 
        if len(carpetas) > 0:
            categoria = carpetas[0].replace('-', ' ').title()
        if len(carpetas) > 1:
            subcategoria = carpetas[1].replace('-', ' ').title()
            
    elif 'product-tag' in partes:
        idx = partes.index('product-tag')
        categoria = "Ofertas Especiales"
        if len(partes) > idx + 1:
            subcategoria = f"Descuento {partes[idx + 1]}%"
            
    return categoria, subcategoria

def iniciar_robot_autonomo():
    print("🚀 ¡Luz verde! Iniciando ciclo de scraping (MODO SEGURO + LOTES)...")
    try:
        respuesta_urls = httpx.get(API_URLS, timeout=120.0)
        lista_urls_db = respuesta_urls.json()
    except Exception as e:
        print(f"❌ Error crítico al obtener URLs: {e}")
        return

    if not lista_urls_db:
        print("⚠️ No hay URLs en la base de datos para procesar.")
        return

    enlaces_a_visitar = [item['url'] for item in lista_urls_db]
    enlaces_a_visitar.sort(key=len, reverse=True)
    
    total_rutas = len(enlaces_a_visitar)
    print(f"🗺️ Se mapearon {total_rutas} rutas principales.")

    timestamp_inicio = datetime.now(timezone.utc).isoformat()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for contador, url_base in enumerate(enlaces_a_visitar, 1):
        pagina_num = 1
        
        while True:
            try:
                url_publica = "https://scraping-tus.onrender.com/"
                httpx.get(url_publica, headers=headers, timeout=10.0)
                print("   💓 Latido externo enviado a Render con éxito.")
            except Exception:
                pass
            # ===================================================================

            url_actual = url_base if pagina_num == 1 else f"{url_base.rstrip('/')}/page/{pagina_num}/"
            print(f"\n[{contador}/{total_rutas}] 🌐 Visitando: {url_actual}")
            
            tiempo_min, tiempo_max = 30.0, 120.0 
            pagina_vacia = True

            try:
                respuesta = httpx.get(url_actual, headers=headers, timeout=15.0)
                
                if respuesta.status_code != 200:
                    if respuesta.status_code == 404 and pagina_num > 1:
                        print("   🏁 Fin de páginas para esta categoría.")
                    else:
                        print(f"   ⚠️ Error {respuesta.status_code} en servidor.")
                    break 
                
                soup = BeautifulSoup(respuesta.text, 'html.parser')
                productos_html = soup.find_all('div', class_='wd-product-wrapper')
                cantidad_productos = len(productos_html)
                
                if cantidad_productos == 0:
                    print("   👻 Sin productos en esta URL.")
                    break 
                
                print(f"   📦 Encontrados {cantidad_productos} productos. Procesando...")
                pagina_vacia = False
                
                cat_actual, subcat_actual = extraer_categorias_dinamicas(url_base)
                lote_productos = []

                for prod in productos_html:
                    h3_tag = prod.find('h3', class_='wd-entities-title')
                    nombre = " ".join(h3_tag.text.split()) if h3_tag else "Sin nombre"
                    
                    print(f"   🔍 Detectado: {nombre[:55]}...")

                    enlace_tag = h3_tag.find('a') if h3_tag else None
                    url_producto = enlace_tag['href'] if enlace_tag else f"sin-url-{nombre}"

                    precio_tag = prod.find('span', class_='price')
                    precio_numerico = limpiar_precio(precio_tag.text if precio_tag else "0")
                    
                    stock_tag = prod.find('p', class_='wd-product-stock')
                    stock_numerico = limpiar_stock(stock_tag.text if stock_tag else "0")

                    lote_productos.append({
                        "url_producto": url_producto,
                        "nombre": nombre,
                        "precio": precio_numerico,
                        "stock": stock_numerico,
                        "categoria": cat_actual,
                        "subcategoria": subcat_actual,
                        "ultima_actualizacion": timestamp_inicio,
                        "activo": True
                    })

                if lote_productos:
                    try:
                        httpx.post(API_PRODUCTOS, json=lote_productos, timeout=60.0)
                        print(f"   ✅ Lote de la página {pagina_num} guardado con éxito.")
                    except Exception as e:
                        print(f"   ❌ Error enviando lote a la API: {e}")

                if cantidad_productos < 18:
                    break 
                else:
                    pagina_num += 1 

            except Exception as e:
                print(f"   ❌ ERROR CRÍTICO en proceso: {e}")
                break 

            finally:
                tiempo_espera = random.uniform(tiempo_min, tiempo_max) 
                if pagina_vacia:
                    espera_corta = random.uniform(5.0, 15.0)
                    print(f"   ⏩ Salto con espera de seguridad... {espera_corta:.1f}s.")
                    time.sleep(espera_corta)
                else:
                    print(f"   ⏳ Simulando lectura humana... pausando {tiempo_espera:.1f}s.")
                    time.sleep(tiempo_espera)

    print("\n🧹 Buscando productos dados de baja...")
    try:
        httpx.post(API_BAJAS, json={"fecha_sync": timestamp_inicio})
    except Exception:
        pass

if __name__ == "__main__":
    iniciar_robot_autonomo()
