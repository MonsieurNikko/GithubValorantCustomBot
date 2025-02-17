import socket

try:
    ip = socket.gethostbyname("www.google.com")
    print("www.google.com résolu en:", ip)
except Exception as e:
    print("Erreur lors de la résolution:", e)
