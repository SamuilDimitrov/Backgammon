import os
from turtle import position
import uuid
import random

from flask import Flask, request, render_template, redirect, url_for, flash
from flask_login import login_user, login_required, current_user, logout_user, LoginManager
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired

from database import db_session, init_db
from models import User

# ------------------------------------------------------------------------------

UPLOAD_FOLDER = ".\\uploads"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = "SECRET_KEY"
app.config.from_pyfile('config.cfg')

# ------------------------------------------------------------------------------

mail = Mail(app)
s = URLSafeTimedSerializer('Thisisasecret!')
init_db()

# ------------------------------------------------------------------------------

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.filter_by(login_id=user_id).first()

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login'))

# ------------------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    return render_template("error_404.html"), 400

# ------------------------------------------------------------------------------

# Row dice
def rowDice():
    dice = [random.randint(1, 6) for i in range(2)]
    return dice

# decide who goes first
def pickStartPlayer():
    diceOnline = rowDice()
    diceIRL = rowDice()
    if diceOnline[0] + diceOnline[1] > diceIRL[0] + diceIRL[1]:
        playerOnTurn = "pWhite"
    elif diceOnline[0] + diceOnline[1] < diceIRL[0] + diceIRL[1]:
        playerOnTurn = "pBlack"
    else:
        playerOnTurn = pickStartPlayer()
    return playerOnTurn

# ------------------------------------------------------------------------------

class BoardPosition:
    def __init__(self, player=None, checkers = 0):
        self.player = player
        self.checkers  = checkers

    def place(self, placing_player):
        if self.player == placing_player:
            self.checkers += 1
        elif self.player is None:
            self.player = placing_player
            self.checkers = 1
        else:
            self.player = placing_player
            return self.player
        return 0

    def removePool(self):
        if self.checkers > 0:
            self.checkers -= 1
            if self.checkers == 0:
                self.player = None

class Game:
    def __init__(self, OnlinePlayer = "pWhite", IRLPlayer = "pBlack"):
        self.OnlinePlayer = OnlinePlayer
        self.IRLPlayer = IRLPlayer
        self.playerOnTurn = pickStartPlayer()
        self.board = [BoardPosition() for i in range(24)]    # the 24 points on the board
        self.barPosition = {"pWhite": 0, "pBlack": 0}        # the plase wghere the checkers that have been hit go
        self.bearingOffStage = {"pWhite": False, "pBlack": False}
        self.bearOffCheckers = {"pWhite": 0, "pBlack": 0}    # the number of checkers that have been beared off
        self.dice = [0, 0]
        self.board[0] = BoardPosition('pBlack', 2)
        self.board[5] = BoardPosition('pWhite', 5)
        self.board[7] = BoardPosition('pWhite', 3)
        self.board[11] = BoardPosition('pBlack', 5)
        self.board[12] = BoardPosition('pWhite', 5)
        self.board[16] = BoardPosition('pBlack', 3)
        self.board[18] = BoardPosition('pBlack', 5)
        self.board[23] = BoardPosition('pWhite', 2)

    # Hit a checker
    def hitChecker(self, playerWhoHasBeenHit):
       self.barPosition[playerWhoHasBeenHit] += 1

    def printBoard(self):
        for i in range(24):
            print(f'{i} - {self.board[i].checkers}')

games = {}

# ------------------------------------------------------------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == "POST":
        username = request.form["username"]
        name = request.form["name"]
        password = request.form["password"]
        confirm_pasword = request.form["verify_password"]
        email = request.form["email"]
        user = User.query.filter_by(username=username).first()
        if(user is not None):
            flash("This username already exists!", "danger")
            return render_template("register.html")
        user = User.query.filter_by(email=email).first()
        if(user is not None):
            flash("This email is already in use!", "danger")
            return render_template("register.html")
        if confirm_pasword == password:
            user = User(username=username, password=generate_password_hash(password), email=email, name=name)
            db_session.add(user)
            db_session.commit()
            user.login_id = str(uuid.uuid4())
            db_session.commit()
            login_user(user)
            flash('You registered and are now logged in. Welcome!', 'success')
            return redirect(url_for('login'))
        else:
            flash("Passwords doesn`t match!","danger")
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'GET':
        return render_template("login.html")
    else:
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            flash("You are logged in!","success")
            user.login_id = str(uuid.uuid4())
            db_session.commit()
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash("Wrong username or password!","danger")
            return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    current_user.login_id = None
    db_session.commit()
    logout_user()
    return redirect(url_for('login'))

# ------------------------------------------------------------------------------

@app.route('/forgotPassword', methods=["GET", "POST"])
def forgotPassword():
    if request.method == 'GET':
        return render_template("forgotPassword.html")
    else:
        user = User.query.filter_by(email=request.form["email"]).first()
        subject = "Password reset requested"
        token = s.dumps(user.email, salt='recover-key')

        msg = Message(subject, sender='kanban.tues@abv.bg', recipients=[user.email])
        link = url_for('reset_with_token', token=token, _external=True)
        msg.body = 'Your link is {}'.format(link)
        mail.send(msg)
        return render_template('check_email.html')

@app.route('/reset/<token>', methods=["GET", "POST"])
def reset_with_token(token):
    try:
        email = s.loads(token, salt="recover-key", max_age=3600)
    except:
        flash('The link is invalid or has expired.', 'danger')
        return redirect(url_for('index'))

    user = User.query.filter_by(email=email).first()
    if request.method == 'POST':
        new_pass = request.form["new_pass"]
        new_pass_conf = request.form["conf_new_pass"]
        if new_pass == new_pass_conf:
            user.password = generate_password_hash(new_pass)

            db_session.add(user)
            db_session.commit()
    else:
        return render_template("recover_password.html")
    return redirect(url_for('login'))

# ------------------------------------------------------------------------------

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
	if request.method == "POST":
		pass
	else:
		return render_template("profile.html")

# ------------------------------------------------------------------------------

@app.route('/uploadPhoto', methods=['POST'])
def uploadPhoto():
    files = request.files
    print(files)
    if 'imageFile' not in request.files:
        return 'there is no imageFile in form!'
    print ("file found")
    file = request.files['imageFile']
    if file:
        filename = file.filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return "OK"

# ------------------------------------------------------------------------------

@app.route('/createGame', methods=['GET', 'POST'])
@login_required
def createGame():
    if request.method == "GET":
        print ("here")
        game_id = str(uuid.uuid4())
        games[game_id] = Game()
    return redirect(url_for('showGame', id = game_id))

@app.route('/showGame/<id>', methods=['GET', 'POST'])
@login_required
def showGame(id):
    if request.method == "GET":
        if id in games: 
            b = games[id].board
            return render_template("showBOard.html", board = b, id = id)
        else:
            return render_template("gameNotFound.html")

@app.route('/ajax', methods = ['POST'])
def ajax_request():
    old_pos_string = request.form['old_pos']
    new_pos_string = request.form['new_pos']
    game_id = request.form['game_id']
    old_pos = int(old_pos_string[6:8])
    new_pos = int(new_pos_string[6:8])
    
    games[game_id].board[old_pos].removePool()
    games[game_id].board[new_pos].place(games[game_id].playerOnTurn)

    allowed = True
    return {'allowed':allowed}

@app.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        return render_template("index.html")
    else:
        return render_template("index_for_non_users.html")
