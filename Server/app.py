from itertools import count
import os
from turtle import position
import uuid
import random
import time

from flask import Flask, request, render_template, redirect, url_for, flash
from flask_login import login_user, login_required, current_user, logout_user, LoginManager
from sqlalchemy import null
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

    def checkIfMoveisPossible(self, placing_player):
        if self.checkers > 1 and self.player != placing_player:
            return -1
        else:
            return 0

    def place(self, placing_player):
        if self.player == placing_player:
            self.checkers += 1
        elif self.player is None:
            self.player = placing_player
            self.checkers = 1
        else:
            if self.checkIfMoveisPossible(placing_player) == 0:
                hittPlayer = self.player
                self.player = placing_player
                return hittPlayer
        return None

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
        self.smallesDiceBear = {"pWhite": 6, "pBlack": 6}
        self.bearOffCheckers = {"pWhite": 0, "pBlack": 0}    # the number of checkers that have been beared off
        self.dice = [0, 0]
        self.doubles = False
        self.board[0] = BoardPosition('pBlack', 2)
        self.board[5] = BoardPosition('pWhite', 5)
        self.board[7] = BoardPosition('pWhite', 3)
        self.board[11] = BoardPosition('pBlack', 5)
        self.board[12] = BoardPosition('pWhite', 5)
        self.board[16] = BoardPosition('pBlack', 3)
        self.board[18] = BoardPosition('pBlack', 5)
        self.board[23] = BoardPosition('pWhite', 2)

    def turnPossible(self):
        if self.barPosition[self.playerOnTurn] == 0:
            return 0
        else:
            new_pos1 = None
            new_pos2 = None
            if self.playerOnTurn == "pWhite":
                new_pos1 = 24 - self.dice[0]
                new_pos2 = 24 - self.dice[1]
            else:
                new_pos1 = self.dice[1] - 1
                new_pos2 = self.dice[0] - 1
             
            if self.board[new_pos1].checkIfMoveisPossible(self.playerOnTurn) == -1 and self.board[new_pos2].checkIfMoveisPossible(self.playerOnTurn) == -1:
                print("no possible move")
                return -1
        return 0

    def upfatesmallesDiceBear(self):
        if self.bearingOffStage[self.playerOnTurn] == True:
            if self.playerOnTurn == "pWhite":
                for i in range (5,-1, -1):
                    if self.board[i].player == self.playerOnTurn:
                        return
                    self.smallesDiceBear[self.playerOnTurn] -= 1
            elif self.playerOnTurn == "pBlack":
                for i in range (19, 24):
                    if self.board[i].player == self.playerOnTurn:
                        return
                    self.smallesDiceBear[self.playerOnTurn] -= 1

    def checkBearingStage(self):
        checkersHome = 0
        counter = None
        if self.playerOnTurn == "pWhite":
            counter = 0;
        elif self.playerOnTurn == "pBlack":
            counter = 18;
        for i in range (6):
            if self.board[counter + i].player == self.playerOnTurn:
                checkersHome += self.board[i].checkers
        if checkersHome == 15:
            self.bearingOffStage[self.playerOnTurn] = True;

    # move checker
    def moveChecker(self, old_position, new_position):
        self.upfatesmallesDiceBear()
        if self.bearingOffStage[self.playerOnTurn] == False:
            self.checkBearingStage()

        if old_position != -1 and old_position != 24:
            if (self.board[old_position].player == "pWhite" and old_position <= new_position) or (self.board[old_position].player == "pBlack" and old_position >= new_position):
                return -1
            
            if self.barPosition[self.playerOnTurn] > 0:
                return -1
        

        if self.board[new_position].checkIfMoveisPossible(self.playerOnTurn) == -1:
            return -1

        tempDice = 0

        if abs(old_position - new_position) == self.dice[0]:
            tempDice = self.dice[0]
            self.dice[0] = 0;
        elif abs(old_position - new_position) == self.dice[1]:
            tempDice = self.dice[1]
            self.dice[1] = 0;
        else:
            if self.bearingOffStage[self.playerOnTurn] == True:
                if self.dice[0] > self.smallesDiceBear[self.playerOnTurn] and (new_position == -1 or new_position == 24):
                    self.dice[0] = 0;
                elif self.dice[1] > self.smallesDiceBear[self.playerOnTurn] and (new_position == -1 or new_position == 24):
                    self.dice[1] = 0;
                else:
                    return -1;
            else:
                return -1;

        if self.dice[0] == 0 and self.dice[1] == 0:
            if self.doubles == True:
                self.doubles = False
                self.dice[0] = tempDice
                self.dice[1] = tempDice
            else:
                self.switchPlayers()

        if old_position != -1 and old_position != 24:
            self.board[old_position].removePool()
        elif old_position == -1 or old_position == 24:
            self.barPosition[self.playerOnTurn] -= 1;

        if self.bearingOffStage[self.playerOnTurn] == True and (new_position == -1 or new_position == 24):
            self.bearOffCheckers[self.playerOnTurn] += 1
        else:
            result = self.board[new_position].place(self.playerOnTurn)
            if result:
                self.barPosition[result] += 1
                return 1
        return 0

    def printBoard(self):
        for i in range(24):
            print(f'{i} - {self.board[i].checkers}')

    def switchPlayers(self):
        if self.playerOnTurn == self.IRLPlayer:
            self.playerOnTurn = self.OnlinePlayer
        else:
            self.playerOnTurn = self.IRLPlayer
    
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
        game_id = str(uuid.uuid4())
        games[game_id] = Game()
    return redirect(url_for('showGame', id = game_id))

@app.route('/showGame/<id>', methods=['GET', 'POST'])
@login_required
def showGame(id):
    if request.method == "GET":
        if id in games: 
            b = games[id].board
            dice = games[id].dice
            playerOnTurn = games[id].playerOnTurn
            bearOffCheckers = games[id].bearOffCheckers
            barPosition = games[id].barPosition
            OnlinePlayer = games[id].OnlinePlayer
            return render_template("showBOard.html", board = b, id = id, dice = dice, playerOnTurn=playerOnTurn, bearOffCheckers = bearOffCheckers, barPosition = barPosition, OnlinePlayer = OnlinePlayer)
        else:
            return render_template("gameNotFound.html")

@app.route('/ajaxDiceRow/<game_id>', methods = ['GET'])
def ajaxDiceRow(game_id):
    games[game_id].dice = rowDice()
    if games[game_id].dice[0] == games[game_id].dice[1]:
        games[game_id].doubles = True
    
    turnPossible = True

    if games[game_id].turnPossible() == -1:
        games[game_id].switchPlayers()
        turnPossible = False
        games[game_id].doubles = False

    return {'dice' : games[game_id].dice, 'turnPossible' : turnPossible, 'currPlayer' : games[game_id].playerOnTurn}

@app.route('/ajaxMove', methods = ['POST'])
def ajax_request():
    old_pos_string = request.form['old_pos']
    new_pos_string = request.form['new_pos']
    game_id = request.form['game_id']

    old_pos = None
    new_pos = None
 
    if old_pos_string == "wHitt":
        old_pos = 24
    elif old_pos_string == "bHitt":
        old_pos = -1
    else:
        old_pos = int(old_pos_string[6:8])
    
    if new_pos_string == "bOut":
        new_pos = 24
    elif new_pos_string == "wOut":
        new_pos = -1
    else:
        if new_pos_string[:6] != "point_":
            return {'allowed' : False, 'currPlayer' : games[game_id].playerOnTurn}
        else:
            new_pos = int(new_pos_string[6:8])

    hitt = False

    result = games[game_id].moveChecker(old_pos,new_pos)

    if result == -1:
        allowed = False
    else:
        allowed = True
        if result == 1:
            hitt = True

    return {'allowed':allowed, 'hitt':hitt, 'dice':games[game_id].dice, 'currPlayer' : games[game_id].playerOnTurn}

@app.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        return render_template("index.html")
    else:
        return render_template("index_for_non_users.html")
