import subprocess
import time
import requests
import json

def teste_sumarizacao():
    """
    Testa a sumarização automática: envia redes adjacentes e verifica 
    se o roteador as uniu na tabela de saída.
    """
    print("=== Iniciando Teste de Sumarização ===")
    
    config_path = 'exemplo/config_A.csv'
    
    print(f"[*] Iniciando roteador na porta 5000 com {config_path}...")
    process = subprocess.Popen([
        'python3', 'roteador.py', 
        '-p', '5000', 
        '-f', config_path, 
        '--network', '10.0.0.0/24',
        '--interval', '5' 
    ])
    
    time.sleep(3)
    
    try:
        """Dados de teste"""
        print("[*] Injetando rotas adjacentes via Bellman-Ford...")
        update_data = {
            "sender_address": "127.0.0.1:5001",
            "routing_table": {
                "10.0.4.0/24": {"cost": 1, "next_hop": "127.0.0.1:5001"},
                "10.0.5.0/24": {"cost": 1, "next_hop": "127.0.0.1:5001"},
                "192.168.10.0/24": {"cost": 2, "next_hop": "127.0.0.1:5001"},
                "192.168.11.0/24": {"cost": 2, "next_hop": "127.0.0.1:5001"}
            }
        }
        
        response = requests.post('http://localhost:5000/receive_update', json=update_data, timeout=5)
        
        if response.status_code == 200:
            print("✅ Rotas injetadas com sucesso!")
            
            print("[*] Aguardando ciclo de sumarização...")
            time.sleep(6)
            
            response = requests.get('http://localhost:5000/routes', timeout=5)
            if response.status_code == 200:
                data = response.json()
                print("\n--- Tabela de Roteamento Atualizada ---")
                print(json.dumps(data['routing_table'], indent=2))

    except Exception as e:
        print(f"❌ Erro durante o teste: {e}")
    finally:
        process.terminate()
        process.wait()
        print("\n[*] Roteador parado. Teste finalizado.")

if __name__ == '__main__':
    teste_sumarizacao()