import yfinance as yf
from functools import lru_cache

class MarketDataService:
    """
    Service pour récupérer les données de marché (prix des actions, taux de change).
    Utilise un cache pour limiter les appels réseau répétés.
    """
    def __init__(self):
        print("INFO: Service de données de marché initialisé.")

    @lru_cache(maxsize=128) # Met en cache les résultats pour ne pas appeler l'API en boucle
    def get_stock_info(self, ticker):
        """Récupère les informations complètes pour un ticker donné."""
        try:
            stock = yf.Ticker(ticker)
            # .info est coûteux, on le fait une fois et on met en cache le résultat
            return stock.info
        except Exception as e:
            print(f"AVERTISSEMENT: Impossible de récupérer les données pour le ticker {ticker}. Erreur: {e}")
            return None

    def get_current_price_and_currency(self, ticker):
        """Retourne le prix actuel et la devise d'un titre."""
        info = self.get_stock_info(ticker)
        if not info:
            return None, None
        
        # Yahoo Finance utilise différentes clés pour le prix, on essaie plusieurs
        price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
        currency = info.get('currency')
        return price, currency

    @lru_cache(maxsize=16) # Met en cache les taux de change
    def get_exchange_rate(self, from_currency, to_currency="EUR"):
        """Récupère le taux de change pour convertir une devise vers l'euro."""
        if from_currency == to_currency:
            return 1.0
        
        # On construit le ticker pour le taux de change, ex: "USDEUR=X"
        pair_ticker = f"{from_currency}{to_currency}=X"
        try:
            pair_info = self.get_stock_info(pair_ticker)
            if pair_info and 'regularMarketPrice' in pair_info:
                rate = pair_info['regularMarketPrice']
                print(f"INFO: Taux de change pour {pair_ticker} récupéré : {rate}")
                return rate
            return None
        except Exception as e:
            print(f"AVERTISSEMENT: Impossible de récupérer le taux de change pour {pair_ticker}. Erreur: {e}")
            return None

    def get_price_in_eur(self, ticker):
        """
        La fonction principale : prend un ticker, récupère son prix
        et sa devise, et le convertit en euros si nécessaire.
        """
        price, currency = self.get_current_price_and_currency(ticker)

        if price is None or currency is None:
            return None # Ticker non trouvé ou données indisponibles

        if currency == "EUR":
            return price # Pas de conversion nécessaire
        else:
            # On doit convertir
            rate = self.get_exchange_rate(currency, "EUR")
            if rate:
                return price * rate
            else:
                # Impossible de trouver le taux de change
                return None