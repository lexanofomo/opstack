import logging
import os
import random
import time
import concurrent.futures
from web3 import Web3


# ============================================
# Логирование с цветной подсветкой
# ============================================
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',  # синий
        'INFO': '\033[92m',  # зеленый
        'WARNING': '\033[93m',  # желтый
        'ERROR': '\033[91m',  # красный
        'CRITICAL': '\033[95m'  # пурпурный
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.msg = f"{color}{record.msg}{self.RESET}"
        return super().format(record)


handler = logging.StreamHandler()
formatter = ColoredFormatter('[%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger()


# ============================================
# Загрузка прокси из файла proxies.txt
# Формат строки: host:port:username:password
# Формируется URL: http://username:password@host:port
# ============================================
def load_proxies(filename="proxies.txt"):
    proxies = []
    if os.path.exists(filename):
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) == 4:
                    host, port, username, password = parts
                    proxy_url = f"http://{username}:{password}@{host}:{port}"
                else:
                    proxy_url = line
                proxies.append(proxy_url)
    return proxies


PROXIES = load_proxies()
if PROXIES:
    logger.info(f"Прокси используются: найдено {len(PROXIES)} прокси.")
else:
    logger.info("Прокси не используются.")

# Глобальный кэш для объектов Web3 по RPC
WEB3_CACHE = {}


def get_web3(rpc):
    if rpc in WEB3_CACHE:
        return WEB3_CACHE[rpc]
    else:
        if PROXIES:
            proxy = random.choice(PROXIES)
            logger.info(f"Используется прокси для {rpc}: {proxy}")
            provider = Web3.HTTPProvider(rpc, request_kwargs={"proxies": {"http": proxy, "https": proxy}})
        else:
            provider = Web3.HTTPProvider(rpc)
        web3_obj = Web3(provider)
        WEB3_CACHE[rpc] = web3_obj
        return web3_obj


# ============================================
# Параметры для сети Base (используем Base для рассылки и сбора)
# ============================================
BASE_NETWORK = {
    "rpc": "https://gateway.tenderly.co/public/base",
    "chain_id": 8453
}
# Для рассылки (Disperse)
SEND_AMOUNT_ETH = 0.001  # фиксированная сумма для рассылки каждому получателю
THRESHOLD_ETH = 0.0000001  # получатель считается пустым, если баланс ниже этого порога
# Для сбора (Collect)
FIXED_GAS_PRICE = 1000000000  # 1 Gwei = 10^9 wei
GAS_LIMIT = 21000
COLLECT_PERCENTAGE = 0.95  # 95%
DELAY_BETWEEN_TX = 0.15  # задержка между транзакциями (сек)


# ============================================
# Функция загрузки кошельков из файла wallets.txt
# Формат строки: address:private_key
# ============================================
def load_wallets(filename="wallets.txt"):
    wallets = []
    if not os.path.exists(filename):
        logger.error(f"Файл {filename} не найден!")
        exit(1)
    with open(filename, "r") as f:
        for line in f:
            if ":" in line:
                addr, key = line.strip().split(":")
                wallets.append((addr.strip(), key.strip()))
    return wallets


# ============================================
# Функция рассылки ETH (Disperse) в сети Base
# Первый кошелек используется как отправитель, остальные – получатели.
# Если баланс получателя меньше порога, отправляется SEND_AMOUNT_ETH.
# ============================================
def disperse_base_transactions(sender, recipients):
    sender_address, sender_key = sender
    w3 = get_web3(BASE_NETWORK["rpc"])
    chain_id = BASE_NETWORK["chain_id"]

    sender_address = Web3.to_checksum_address(sender_address)
    sender_nonce = w3.eth.get_transaction_count(sender_address, 'pending')
    logger.info(f"Рассылка: Отправитель {sender_address} - текущий nonce: {sender_nonce}")
    success_count = 0

    for idx, recipient in enumerate(recipients, start=1):
        rec_address, _ = recipient
        rec_address = Web3.to_checksum_address(rec_address)
        balance = w3.eth.get_balance(rec_address)
        balance_eth = float(w3.from_wei(balance, "ether"))
        if balance_eth < THRESHOLD_ETH:
            logger.info(f"Рассылка: Получатель {rec_address} уже имеет баланс {balance_eth:.6f} ETH, пропуск.")
            continue

        tx = {
            'nonce': sender_nonce,
            'to': rec_address,
            'value': Web3.to_wei(SEND_AMOUNT_ETH, "ether"),
            'gas': GAS_LIMIT,
            'gasPrice': w3.eth.gas_price,
            'chainId': chain_id
        }
        retries = 3
        while retries > 0:
            try:
                signed_tx = w3.eth.account.sign_transaction(tx, sender_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                logger.info(
                    f"Рассылка: TX {Web3.to_hex(tx_hash)} отправлена на {rec_address} ({idx}/{len(recipients)})")
                success_count += 1
                sender_nonce += 1
                break
            except Exception as e:
                logger.warning(
                    f"Рассылка: Ошибка при отправке с {sender_address} на {rec_address}: {str(e)}. Повтор через 3 с...")
                time.sleep(3)
                retries -= 1
        if retries == 0:
            logger.error(f"Рассылка: Не удалось отправить TX на {rec_address} после нескольких попыток.")
        time.sleep(DELAY_BETWEEN_TX)

    final_nonce = w3.eth.get_transaction_count(sender_address, 'pending')
    logger.info(f"Рассылка завершена: успешно отправлено {success_count} TX (общий nonce: {final_nonce}).")
    return success_count


# ============================================
# Функция сбора ETH (Collect) в сети Base
# Для каждого донорского кошелька отправляется 95% от (баланса - стоимость газа)
# Если транзакция не подтверждается в течение 10 секунд, повышаем gasPrice на 20% и повторяем,
# обновляя nonce из сети, чтобы закрыть зависшую транзакцию.
# ============================================
def collect_eth(main_wallet, donor_wallets, gas_limit=GAS_LIMIT, fixed_gas_price=FIXED_GAS_PRICE,
                percentage=COLLECT_PERCENTAGE):
    w3 = get_web3(BASE_NETWORK["rpc"])
    chain_id = BASE_NETWORK["chain_id"]
    main_address = Web3.to_checksum_address(main_wallet[0])
    collected_txs = []

    for donor in donor_wallets:
        donor_address, donor_key = donor
        donor_address = Web3.to_checksum_address(donor_address)
        balance = w3.eth.get_balance(donor_address)
        gas_cost = gas_limit * fixed_gas_price
        if balance <= gas_cost:
            logger.info(f"Сбор: Кошелек {donor_address} имеет недостаточно средств для оплаты газа.")
            continue
        amount_to_send = int(percentage * (balance - gas_cost))
        if amount_to_send <= 0:
            logger.info(f"Сбор: Кошелек {donor_address} не имеет средств для перевода после вычета газа.")
            continue

        # Получаем начальный nonce (с учетом pending)
        nonce = w3.eth.get_transaction_count(donor_address, 'pending')
        current_gas_price = fixed_gas_price
        tx = {
            'nonce': nonce,
            'to': main_address,
            'value': amount_to_send,
            'gas': gas_limit,
            'gasPrice': current_gas_price,
            'chainId': chain_id
        }
        retries = 3
        sent = False
        while retries > 0:
            try:
                # Не изменяем nonce, используем фиксированное значение
                tx['nonce'] = nonce
                tx['gasPrice'] = current_gas_price
                signed_tx = w3.eth.account.sign_transaction(tx, donor_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                logger.info(
                    f"Сбор: TX отправлена с {donor_address} на {main_address}: {Web3.to_hex(tx_hash)}. Ожидание подтверждения (10 сек)...")
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=10)
                if receipt and receipt.status == 1:
                    logger.info(f"Сбор: TX {Web3.to_hex(tx_hash)} подтверждена. Receipt: {receipt}")
                    collected_txs.append(tx_hash)
                    sent = True
                    break
                else:
                    raise Exception("TX не подтверждена")
            except Exception as e:
                logger.warning(
                    f"Сбор: Ошибка при отправке TX с {donor_address} (nonce {nonce}): {str(e)}. Повтор через 3 сек...")
                time.sleep(3)
                retries -= 1
                if retries > 0:
                    if "nonce too low" in str(e).lower():
                        new_nonce = w3.eth.get_transaction_count(donor_address, 'pending')
                        logger.warning(f"Сбор: Обновление nonce с {nonce} до {new_nonce} для {donor_address}.")
                        nonce = new_nonce
                    else:
                        current_gas_price = int(current_gas_price * 1.2)
                        logger.info(
                            f"Сбор: Повышение gasPrice до {current_gas_price} wei для {donor_address} с nonce {nonce}.")
                        tx['gasPrice'] = current_gas_price
        if not sent:
            logger.error(
                f"Сбор: Не удалось отправить TX с {donor_address} с nonce {nonce} после нескольких попыток. Устанавливаю nonce в -1.")
            nonce = -1
        time.sleep(DELAY_BETWEEN_TX)

    logger.info(f"Сбор завершен. Отправлено транзакций: {len(collected_txs)}")
    return collected_txs


# ============================================
# Главный блок
# ============================================
if __name__ == "__main__":
    wallets = load_wallets("wallets.txt")
    if len(wallets) < 2:
        logger.error(
            "Для работы необходимо минимум 2 кошелька в wallets.txt (один отправитель и хотя бы один получатель/донор).")
        exit(1)

    logger.info(f"Найдено кошельков: {len(wallets)}")
    logger.info("Выберите режим работы:")
    logger.info(
        "1 - Рассылка ETH (Disperse): отправитель – первый кошелек, остальные – получатели (если баланс получателя ниже порога).")
    logger.info("2 - Сбор ETH (Collect): основной кошелек – первый, доноры – остальные.")
    mode = input("Введите 1 или 2: ").strip()

    if mode == "1":
        sender_wallet = wallets[0]
        recipient_wallets = wallets[1:]
        logger.info(f"Рассылка в сети Base. Отправитель: {sender_wallet[0]}, получателей: {len(recipient_wallets)}")
        disperse_base_transactions(sender_wallet, recipient_wallets)
    elif mode == "2":
        main_wallet = wallets[0]
        donor_wallets = wallets[1:]
        logger.info(f"Сбор ETH в сети Base. Основной кошелек: {main_wallet[0]}, доноров: {len(donor_wallets)}")
        collect_eth(main_wallet, donor_wallets)
    else:
        logger.error("Неверный режим. Завершение работы.")
        exit(1)

    input("\nНажмите Enter, чтобы выйти...")
