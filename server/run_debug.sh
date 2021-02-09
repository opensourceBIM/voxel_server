export FLASK_APP=main.py
export FLASK_DEBUG=1
export FLASK_ENV=development
export VOXEC_EXE=voxec
python3 -m flask run -h 0.0.0.0 -p 5555
