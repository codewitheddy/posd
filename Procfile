release: python manage.py migrate
web: gunicorn pos_system.wsgi --log-file - --timeout 120 --workers 2
