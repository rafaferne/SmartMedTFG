# Gemelo digital humano para planes de cuidado con wearables y LLMs en web

Plataforma de cuidados para pacientes con alguna enfermedad para la evaluación del estado de salud a traves de informes proporcionados por wearables. Generación de un gemelo digital humano para el estudio de estos datos y proporcionar intervenciones adecuadas al paciente

## 🧠 Tutorial de Configuración del Proyecto

### 1. Clonar el repositorio:
Abre una terminal y ejecuta el siguiente comando para clonar el repositorio del proyecto:

```bash
git clone https://github.com/rafaferne/SmartMedTFG.git
```

### 2. Obtener API Key de Google Gemini
Entrar en [ApiKey](https://aistudio.google.com/api-keys) y crear una APIKEY.

Copiar la APIKEY y pegarla en el apartado de "LLM_API_KEY" de /backend/.env

### 3. Entrar en la carpeta del proyecto y ejecutar Docker

```bash
cd SmartMedTFG

docker compose up -d
```
### 4. Acceder a la pagina usando la URL

Poner este link en el buscador y listo: [SmartMed](http://localhost/)