import requests

url ="https://api.open-meteo.com/v1/forecast"

params = {
    "latitude": 4.791603,
    "longitude":-75.689187,
     "current":"temperature_2m",
    "timezone" : "America/Bogota"

}
peticion = requests.get(url,params=params)
if peticion.status_code == 200:
    respuesta = peticion.json()
    #print(respuesta.keys())
    print(respuesta.get("current").get("time"))
    print(respuesta.get("current").get("temperature_2m"))
