psql --host 127.0.0.1 -p 5432 -U el21 -d postgres -c 'drop database backend'
psql --host 127.0.0.1 -p 5432 -U el21 -d postgres -c "create database backend"
python manage.py migrate
python manage.py runserver