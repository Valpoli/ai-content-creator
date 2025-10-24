import json
import os
import time

import requests
import yaml
from dotenv import load_dotenv
from openai import OpenAI


class LLMClient:
    def __init__(self, config_path="config.yaml"):
        load_dotenv()
        self.endpoint = "https://models.inference.ai.azure.com"
        self.token = os.getenv("GITHUB_TOKEN")

        self.model_name_mistral = "mistral-small-2503"
        self.model_name_openai = "gpt-4o"

        self.headers_mistral = {"Content-Type": "application/json", "api-key": self.token}

        self.url_mistral = f"{self.endpoint}/chat/completions?api-version=2023-12-01-preview"
        self.config = self._load_config(config_path)

    def _load_config(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Fichier de configuration introuvable : {path}")
        with open(path, encoding="utf-8") as file:
            return yaml.safe_load(file)

    def chat(self, model: str, user_prompt: str, system_prompt: str = "Tu es un assistant intelligent et utile.") -> str:
        if model == "mistral":
            return self._chat_with_mistral(system_prompt, user_prompt)
        elif model == "openai":
            return self._chat_with_openai(system_prompt, user_prompt)
        else:
            raise ValueError(f"Modèle inconnu : {model}")

    def _chat_with_mistral(self, system_prompt, user_prompt):
        body = {
            "model": self.model_name_mistral,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": 1.0,
            "top_p": 1.0,
            "max_tokens": 1000,
        }

        max_retries = 3
        retry_delay = 5  # secondes entre les essais

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(self.url_mistral, headers=self.headers_mistral, json=body)
                response.raise_for_status()
                data = response.json()

                time.sleep(3)
                if "choices" in data and data["choices"] and "message" in data["choices"][0]:
                    return data["choices"][0]["message"].get("content", None)
                else:
                    print("❌ Réponse inattendue de Mistral :")
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                    return None

            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:
                    print(f"⚠️ Tentative {attempt} : Trop de requêtes. Nouvelle tentative dans {retry_delay} secondes...")
                    time.sleep(retry_delay)
                    continue  # on réessaie
                else:
                    print("💥 Erreur Mistral :", e)
                    return None

            except Exception as e:
                print("💥 Erreur Mistral :", e)
                return None

        print("❌ Échec après 3 tentatives. Abandon.")
        return None

    def _chat_with_openai(self, system_prompt, user_prompt):
        client = OpenAI(base_url=self.endpoint, api_key=self.token)

        max_retries = 3
        retry_delay = 5  # secondes d’attente entre les essais

        for attempt in range(1, max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self.model_name_openai,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    temperature=1.0,
                    top_p=1.0,
                    max_tokens=1000,
                )
                time.sleep(3)
                return response.choices[0].message.content

            except OpenAI.RateLimitError:
                print(f"⚠️ Tentative {attempt} : Trop de requêtes vers OpenAI. Nouvelle tentative dans {retry_delay} secondes...")
                time.sleep(retry_delay)
                continue

            except Exception as e:
                print("💥 Erreur OpenAI :", e)
                return None

        print("❌ Échec après 3 tentatives. Abandon.")
        return None
