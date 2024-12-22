from flask import Flask, request, render_template
import requests
import plotly.express as px
import dash
from dash import html
from dash import dcc, ctx
from dash.dependencies import Input, Output
import pandas as pd

# Ваш ключ API AccuWeather
API_KEY = 'yGBhYW3XIclR9eAdAc275UgcBecZXy6i'

# Инициализация Flask приложения
app = Flask(__name__)

# Инициализация Dash внутри Flask
dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dash/')

# Глобальная переменная для хранения списка городов
cities = []

import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)

def get_coordinates(city_name):
    url = f'http://dataservice.accuweather.com/locations/v1/cities/search'
    params = {
        'apikey': API_KEY,
        'q': city_name,
        'language': 'ru-ru'
    }

    try:
        response = requests.get(url, params=params)
        logging.info(f"Запрос к API для города: {city_name}, статус: {response.status_code}")

        if response.status_code != 200:
            return None, None, f"Ошибка при получении координат: HTTP статус {response.status_code}"

        data = response.json()
        if not data:
            return None, None, f"Нет данных о местоположении для города: {city_name.strip()}"

        return data[0]['GeoPosition']['Latitude'], data[0]['GeoPosition']['Longitude'], None

    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при подключении к серверу: {str(e)}")
        return None, None, f"Ошибка при подключении к серверу: {str(e)}"




# Функция для получения ключа местоположения
def get_location_key(latitude, longitude):
    url = 'http://dataservice.accuweather.com/locations/v1/cities/geoposition/search'
    params = {
        'apikey': API_KEY,
        'q': f'{latitude},{longitude}',
        'language': 'ru-ru'
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None

    data = response.json()
    return data['Key'] if 'Key' in data else None

def get_forecast(location_key):
    url = f'http://dataservice.accuweather.com/forecasts/v1/daily/5day/{location_key}'
    params = {
        'apikey': API_KEY,
        'language': 'ru-ru',
        'details': 'true',
        'metric': 'true'
    }
    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"Ошибка при получении прогноза погоды: {response.status_code}, {response.text}")
        return None

    data = response.json()
    if 'DailyForecasts' not in data:
        print("Ошибка: Нет данных о прогнозе погоды")
        return None

    return data

def extract_weather_parameters(weather_data):
    try:
        temperature_celsius = weather_data['Temperature']['Maximum']['Value']
        wind_speed = weather_data['Day']['Wind']['Speed']['Value']
        humidity_percent = weather_data['Day'].get('RelativeHumidity', 'Не доступно')
        rain_probability = weather_data['Day'].get('PrecipitationProbability', 'Не доступно')
        date = weather_data['Date']  # Добавляем дату
    except KeyError as e:
        print(f"Ошибка извлечения данных: {e}")
        return None

    return {
        'date': date,  # Возвращаем дату
        'temperature': temperature_celsius,
        'humidity': humidity_percent,
        'wind_speed': wind_speed,
        'rain_probability': rain_probability
    }

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/weather', methods=['POST'])
def weather():
    global cities  # Указываем, что мы используем глобальную переменную
    start_city = request.form.get('start_city')
    end_city = request.form.get('end_city')
    intermediate_cities = request.form.getlist('intermediate_city')

    # Собираем все города в один список
    cities = [start_city] + intermediate_cities + [end_city]

    # Проверка на пустоту списка
    if not cities or all(city.strip() == "" for city in cities):
        return render_template('result.html', weather_condition="Пожалуйста, введите хотя бы один город.")

    weather_data = {}

    for city in cities:
        # Получаем координаты для каждого города
        latitude, longitude, error_message = get_coordinates(city)
        if error_message:
            return render_template('result.html', weather_condition=error_message)

        # Получаем ключ местоположения
        location_key = get_location_key(latitude, longitude)
        if not location_key:
            return render_template('result.html',
                                   weather_condition=f"Не удалось получить ключ местоположения для {city}")

        # Получаем прогноз погоды
        forecast = get_forecast(location_key)
        if not forecast:
            return render_template('result.html', weather_condition="Ошибка при получении прогноза погоды")

        # Извлекаем данные о погоде
        weather_data[city] = [extract_weather_parameters(day) for day in forecast['DailyForecasts']]

    # Возвращаем результаты в шаблон, включая список городов
    return render_template('result.html', weather_data=weather_data, cities=cities)


dash_app.layout = html.Div([
    html.H1("Прогноз погоды для городов"),
    dcc.RadioItems(
        id='days-radio',
        options=[
            {'label': '3 дня', 'value': 3},
            {'label': '5 дней', 'value': 5},
            {'label': '7 дней', 'value': 7}
        ],
        value=5,  # Значение по умолчанию
        labelStyle={'display': 'inline-block'}
    ),
    dcc.Checklist(
        id='weather-parameters',
        options=[
            {'label': 'Температура', 'value': 'temperature'},
            {'label': 'Скорость ветра', 'value': 'wind_speed'},
            {'label': 'Вероятность осадков', 'value': 'rain_probability'}
        ],
        value=['temperature'],  # Значение по умолчанию
        inline=True
    ),
    dcc.Graph(id='weather-graph')  # График для отображения погоды
])


@dash_app.callback(
    Output('weather-graph', 'figure'),
    [Input('days-radio', 'value'),
     Input('weather-parameters', 'value')]
)
def update_graph(days, selected_parameters):
    if not cities:
        return px.line(title="Нет данных для отображения")

    # Создаем пустой список для хранения данных
    all_weather_data = []

    for city in cities:
        # Получаем данные для каждого города
        latitude, longitude, error_message = get_coordinates(city)
        if error_message:
            print(f"Ошибка получения координат для города {city}: {error_message}")
            continue  # Пропускаем город, если произошла ошибка

        location_key = get_location_key(latitude, longitude)
        if not location_key:
            print(f"Не удалось получить ключ местоположения для города {city}")
            continue  # Пропускаем город, если ключ не получен

        forecast = get_forecast(location_key)
        if not forecast:
            print(f"Ошибка при получении прогноза погоды для города {city}")
            continue  # Пропускаем город, если прогноз не получен

        # Извлекаем данные о погоде
        weather_data = [extract_weather_parameters(day) for day in forecast['DailyForecasts'][:days]]
        days_list = [day['Date'] for day in forecast['DailyForecasts'][:days]]

        # Проверка, что данные о погоде не пустые
        if not weather_data:
            print(f"Нет данных о погоде для города {city}")
            continue  # Пропускаем город, если нет данных

        # Добавляем данные в общий список
        for day_data in weather_data:
            day_data['city'] = city  # Добавляем название города
            all_weather_data.append(day_data)

    # Проверка, что данные не пустые
    if not all_weather_data:
        print("Нет данных для отображения на графике.")
        return px.line(title="Нет данных для отображения")

    # Создаем DataFrame для построения графиков
    df = pd.DataFrame(all_weather_data)
    df['Date'] = pd.to_datetime(df['date'])

    # Проверка содержимого DataFrame
    print("Данные для графика:", df)

    # Проверка наличия выбранных параметров
    for param in selected_parameters:
        if param not in df.columns:
            print(f"Параметр {param} отсутствует в данных.")
            return px.line(title="Нет данных для отображения")

    # Создаем график с выбранными параметрами
    fig = px.line(df, x='Date', y=selected_parameters,
                  color='city',  # Используем цвет для различия городов
                  title='Прогноз погоды для городов',
                  labels={'value': 'Значение', 'variable': 'Параметр'},
                  markers=True)

    # Добавляем всплывающие подсказки
    fig.update_traces(mode='lines+markers', hovertemplate='%{x}: %{y:.2f}')

    return fig



if __name__ == '__main__':
    app.run(debug=True)

