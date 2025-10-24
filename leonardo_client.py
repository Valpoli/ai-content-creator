import os

import requests
import yaml
from databases.image_database import ImageDatabase
from dotenv import load_dotenv


class LeonardoClient:
    def __init__(self, config_path="config.yaml"):
        load_dotenv()
        self.token = os.getenv("LEONARDO_API_KEY")
        self.headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {self.token}"}

        self.image_db = ImageDatabase()

        self.url_generate = "https://cloud.leonardo.ai/api/rest/v1/generations"
        self.url_me = "https://cloud.leonardo.ai/api/rest/v1/me"
        self.url_pricing = "https://cloud.leonardo.ai/api/rest/v1/pricing-calculator"
        self.url_base_generation = "https://cloud.leonardo.ai/api/rest/v1/generations/"

        self.global_story_folder = "histoire/"

        self.config = self._load_config(config_path)

        self.width = 1024
        self.height = 768
        self.num_images = 1
        self.inference_steps = 15
        self.prompt_magic = False
        self.alchemy_mode = False
        self.high_resolution = True
        self.is_custom_model = False
        self.is_sdxl = False
        self.model_id = "b24e16ff-06e3-43eb-8d33-4416c2d75876"
        self.preset_style = "ANIME"

    def _load_config(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"❌ Fichier de config introuvable : {path}")
            return {}

    def get_user_data(self):
        response = requests.get(self.url_me, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            print("❌ Token invalide :", response.text)
            return None

    def print_user_info(self):
        data = self.get_user_data()
        if not data:
            return
        try:
            details = data["user_details"][0]
            user = details.get("user", {})
            print("\n📄 Infos Utilisateur Leonardo.ai")
            print("────────────────────────────────")
            print(f"👤 Username: {user.get('username')}")
            print(f"🆔 ID: {user.get('id')}")
            # print(f"💰 Paid Tokens: {details.get('paidTokens')}")
            # print(f"🎁 Subscription Tokens: {details.get('subscriptionTokens')}")
            # print(f"🧠 GPT Tokens: {details.get('subscriptionGptTokens')}")
            # print(f"📚 Model Tokens: {details.get('subscriptionModelTokens')}")
            print(f"📚 Tokens available: {details.get('apiSubscriptionTokens')}")
            # print(f"🚦 API Slots: {details.get('apiConcurrencySlots')}")
            print("────────────────────────────────\n")
        except Exception as e:
            print(f"❌ Erreur lors du parsing utilisateur : {e}")

    def calculate_image_price(self):
        payload = {
            "serviceParams": {
                "IMAGE_GENERATION": {
                    "imageHeight": self.height,
                    "imageWidth": self.width,
                    "numImages": self.num_images,
                    "inferenceSteps": self.inference_steps,
                    "promptMagic": self.prompt_magic,
                    "alchemyMode": self.alchemy_mode,
                    "highResolution": self.high_resolution,
                    "isModelCustom": self.is_custom_model,
                    "isSDXL": self.is_sdxl,
                }
            },
            "service": "IMAGE_GENERATION",
        }
        try:
            response = requests.post(self.url_pricing, headers=self.headers, json=payload)
            response.raise_for_status()
            cost = response.json()["calculateProductionApiServiceCost"]["cost"]
            print(f"💸 Prix par image : {cost} tokens")
            return cost
        except Exception as e:
            print("❌ Erreur pricing :", e)
            return None

    def get_total_cost(self, number_of_images):
        cost_per_image = self.calculate_image_price()
        if cost_per_image is None:
            return None
        total = cost_per_image * number_of_images
        print(f"🧮 Coût total pour {number_of_images} image(s) : {total} tokens")
        return total

    def generate_image(self, epc, prompt, negative_prompt):
        max_length = 1400
        prompt = prompt[:max_length]
        negative_prompt = negative_prompt[:max_length]

        def send_request(prompt_to_use, negative_to_use):
            payload = {
                "alchemy": self.alchemy_mode,
                "height": self.height,
                "modelId": self.model_id,
                "num_images": self.num_images,
                "presetStyle": self.preset_style,
                "prompt": prompt_to_use,
                "negative_prompt": negative_to_use,
                "width": self.width,
                "promptMagic": self.prompt_magic,
                "num_inference_steps": self.inference_steps,
                "highResolution": self.high_resolution,
            }
            return requests.post(self.url_generate, headers=self.headers, json=payload)

        try:
            response = send_request(prompt, negative_prompt)

            if response.status_code == 200:
                print("✅ Image générée avec succès.")
                self.image_db.add_entry(
                    epc,
                    self.width,
                    self.height,
                    self.inference_steps,
                    self.prompt_magic,
                    self.alchemy_mode,
                    self.high_resolution,
                    self.is_custom_model,
                    self.is_sdxl,
                    prompt,
                    negative_prompt,
                    self.model_id,
                    self.preset_style,
                )
            elif response.status_code == 403:
                print("❌ Prompt refusé (403) ! On régénère une voiture cool et swag à la place.")
                car_prompt = "a futuristic cool and swag car, shiny chrome, cyberpunk style, neon lights, cinematic lighting"
                car_negative = "blurry, low quality, distorted"
                response = send_request(car_prompt, car_negative)

                if response.status_code == 200:
                    print("✅ Image de voiture swag générée en remplacement.")
                    self.image_db.add_entry(
                        epc,
                        self.width,
                        self.height,
                        self.inference_steps,
                        self.prompt_magic,
                        self.alchemy_mode,
                        self.high_resolution,
                        self.is_custom_model,
                        self.is_sdxl,
                        car_prompt,
                        car_negative,
                        self.model_id,
                        self.preset_style,
                    )
                else:
                    print(f"❌ Erreur lors de la génération de la voiture : {response.status_code} - {response.text}")

            else:
                print(f"❌ Erreur génération : {response.status_code} - {response.text}")

            return response

        except Exception as e:
            print("❌ Exception lors de la génération :", e)
            return None

    def get_generation_info(self, generation_id):
        url = self.url_base_generation + generation_id
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Erreur récupération info génération {generation_id}: {response.status_code}")
            return None

    def download_images(self, data, story_folder, epc):
        generation_data = data.get("generations_by_pk", {})
        images = generation_data.get("generated_images", [])

        if not images:
            print("⚠️ Aucune image dans la génération.")
            return

        output_dir = os.path.join(self.global_story_folder, story_folder, "img")
        os.makedirs(output_dir, exist_ok=True)

        for img in images:
            url = img.get("url")
            image_id = img.get("id")
            ext = os.path.splitext(url)[-1] or ".jpg"
            filename = f"{epc}{ext}"
            filepath = os.path.join(output_dir, filename)

            try:
                img_response = requests.get(url)
                img_response.raise_for_status()
                with open(filepath, "wb") as f:
                    f.write(img_response.content)
                print(f"📥 Image téléchargée : {filename}")
            except Exception as e:
                print(f"❌ Échec téléchargement image {image_id} : {e}")
