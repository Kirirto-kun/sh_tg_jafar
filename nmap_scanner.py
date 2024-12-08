from flask import Flask, request, jsonify
import nmap
import socket  # Для преобразования доменов в IP

app = Flask(__name__)
nm = nmap.PortScanner()

def resolve_domain_to_ip(domain):
    """Преобразуем доменное имя в IP-адрес."""
    try:
        ip_address = socket.gethostbyname(domain)
        return ip_address
    except socket.error as e:
        return None


@app.route('/scan', methods=['POST'])
def scan():
    try:
        # Получаем адрес из запроса
        data = request.get_json()
        address = data.get('address')
        
        if not address:
            return jsonify({"error": "No address provided"}), 400

        # Проверяем, является ли это IP-адресом или доменом
        if address.replace(".", "").isdigit():  # Простая проверка на IP
            ip_address = address
        else:
            ip_address = resolve_domain_to_ip(address)  # Преобразуем домен в IP

        if not ip_address:
            return jsonify({"error": "Could not resolve domain to IP"}), 400
        
        # Сканирование IP с Nmap
        nm.scan(hosts=ip_address, arguments='-T4 -F', timeout=30)

        # Проверяем, есть ли хосты в результате сканирования
        if ip_address not in nm.all_hosts():
            return jsonify({"error": "No hosts found during scan"}), 404

        # Возвращаем порты и сервисы
        scan_result = {
            "IP": ip_address,
            "hosts": nm.all_hosts(),
            "ports": [
                {
                    "port": port,
                    "protocol": nm[ip_address]['tcp'][port]['name'],
                    "state": nm[ip_address]['tcp'][port]['state']
                }
                for port in nm[ip_address]['tcp']
            ]
        }

        return jsonify(scan_result), 200

    except Exception as e:
        # Обработка ошибок и возвращение информации о сбое
        return jsonify({"error": str(e)}), 500

@app.route('/scan_ip', methods=['POST'])
def scan_ip():
    # Получаем IP из данных пользователя
    data = request.get_json()
    ip_address = data.get('ip')

    if not ip_address:
        return jsonify({"error": "IP address is required"}), 400

    try:
        # Сканируем с использованием Nmap
        nm.scan(hosts=ip_address, arguments='-T4 -F', timeout=30)
        
        # Формируем ответ
        scan_result = {
            "IP": ip_address,
            "hosts": nm.all_hosts(),
            "ports": [
                {
                    "port": port,
                    "protocol": nm[ip_address]['tcp'][port]['name'],
                    "state": nm[ip_address]['tcp'][port]['state']
                }
                for port in nm[ip_address]['tcp']
            ]
        }

        return jsonify(scan_result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500






def scan_ports(ip_address):
    """Сканируем порты на IP-адресе от 1 до 1024."""
    open_ports = []
    ports = [20, 22, 53, 80, 443, 8000, 8080, 5432, 5001, 3000, 4000]
    for port in ports:  # Проверяем порты от 1 до 1024
        try:
            # Пытаемся подключиться к порту
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)  # Timeout для предотвращения зависаний
                s.connect((ip_address, port))
                open_ports.append(port)
        except (socket.timeout, ConnectionRefusedError):
            continue
    return open_ports


@app.route('/scan_for_ports', methods=['POST'])
def scan_for_ports():
    try:
        # Получаем данные от пользователя
        data = request.get_json()
        address = data.get('address')

        if not address:
            return jsonify({"error": "Address is required"}), 400

        # Проверяем, является ли это IP или домен
        try:
            ip_address = socket.gethostbyname(address)
        except socket.error:
            return jsonify({"error": "Could not resolve domain to IP"}), 400

        # Сканируем порты
        open_ports = scan_ports(ip_address)

        # Возвращаем результат
        return jsonify({
            "address": address,
            "resolved_ip": ip_address,
            "open_ports": open_ports
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True)
