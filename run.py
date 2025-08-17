from robot.api import create_app

app = create_app()

if __name__ == "__main__":
    # host/port — как у тебя было
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
