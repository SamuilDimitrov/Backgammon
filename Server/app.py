import os
import uuid
import random
import json
from datetime import datetime, timedelta
from time import sleep

from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, abort
from flask_login import login_user, login_required, current_user, logout_user, LoginManager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask_socketio import SocketIO, join_room, send, emit, leave_room


from database import db_session, init_db
from models import User, Device

# ------------------------------------------------------------------------------

UPLOAD_FOLDER = ".\\uploads"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = "SECRET_KEY"
app.config.from_pyfile('config.cfg')

# ------------------------------------------------------------------------------

mail = Mail(app)
socketio = SocketIO(app)
s = URLSafeTimedSerializer('Thisisasecret!')

# ------------------------------------------------------------------------------

init_db()
d = Device.query.all()
u = User.query.all()
if len(d) == 0:
    devicesIdsFile = open('deviceID.txt', 'r')
    deviceIDs = devicesIdsFile.readlines() 
    for deviceID in deviceIDs:
        newDevice = Device(deviceId=deviceID)
        db_session.add(newDevice)
        db_session.commit()

if len(u) == 0:
    user = user = User(username="test1", password=generate_password_hash("1234"), email="a@b", name="GG")
    db_session.add(user)
    db_session.commit()

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
    return render_template("error_404.html"), 404

# ------------------------------------------------------------------------------

games = {}
numberDevicesConected = 0
gameId_device = {}

# ------------------------------------------------------------------------------

@socketio.on('connect')
def on_connect():
    print("Someone is trying to conect")
    global numberDevicesConected
    numberDevicesConected += 1
    # send("Someone had connected", broadcast=True)

# @socketio.on('connectingDevice')
# def on_connectingDevice(deviceId):
#     conectingDevice = Device.query.filter_by(deviceId=deviceId).first()
#     conectingDevice.status = "connected"
#     db_session.commit()
#     device_socket[deviceId] = request.sid
#     print(device_socket)

@socketio.on('disconnect')
def on_disconnect():
    # disconectedDeviceId = device_socket[list(device_socket.keys())[list(device_socket.values()).index(request.sid)]]
    # disconectedDevice = Device.query.filter_by(deviceId=disconectedDeviceId).first()
    # disconectedDevice.status = "disconnected"
    # db_session.commit()
    # device_socket.pop(disconectedDeviceId)
    global numberDevicesConected
    numberDevicesConected -= 1

@socketio.on('message')
def handleMessage(msg):
    print('Message:', str(msg))
    send(msg)


@socketio.on('join')
def on_join(data):
    client_nubmer = random.randint(1000, 100000)
    username = "Board #: " + str(client_nubmer)
    game_id = data['game_id']    
    print("Game ID = ")
    print(game_id)
    join_room(game_id)
    emit("guests_names", {"oponent" : username}, to=game_id)

@socketio.on('leave')
def on_leave(data):
    username = data['username']
    game_id = data['game_id']
    leave_room(game_id)
    send(username + ' has left the room.', to=game_id)

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
        self.moveDirection = []
        self.deviceReady = False
        self.OnlinePlayer = OnlinePlayer
        self.gameEnd = False
        self.IRLPlayer = IRLPlayer
        self.playerOnTurn = "pWhite"
        # self.playerOnTurn = pickStartPlayer()
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

    def updatesmallesDiceBear(self):
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
    def moveChecker(self, oldPosition, newPosition):
        if self.gameEnd == True:
            return -1
        self.updatesmallesDiceBear()
        if self.bearingOffStage[self.playerOnTurn] == False:
            self.checkBearingStage()

        if oldPosition != -1 and oldPosition != 24:
            if (self.board[oldPosition].player == "pWhite" and oldPosition <= newPosition) or (self.board[oldPosition].player == "pBlack" and oldPosition >= newPosition):
                return -1
            
            if self.barPosition[self.playerOnTurn] > 0:
                return -1
        
        if self.board[newPosition].checkIfMoveisPossible(self.playerOnTurn) == -1:
            return -1

        tempDice = 0

        if abs(oldPosition - newPosition) == self.dice[0]:
            tempDice = self.dice[0]
            self.dice[0] = 0;
        elif abs(oldPosition - newPosition) == self.dice[1]:
            tempDice = self.dice[1]
            self.dice[1] = 0;
        else:
            if self.bearingOffStage[self.playerOnTurn] == True:
                if self.dice[0] > self.smallesDiceBear[self.playerOnTurn] and (newPosition == -1 or newPosition == 24):
                    self.dice[0] = 0;
                elif self.dice[1] > self.smallesDiceBear[self.playerOnTurn] and (newPosition == -1 or newPosition == 24):
                    self.dice[1] = 0;
                else:
                    return -1;
            else:
                return -1;

        function_Result = 0

        if oldPosition != -1 and oldPosition != 24:
            self.board[oldPosition].removePool()
        elif oldPosition == -1 or oldPosition == 24:
            self.barPosition[self.playerOnTurn] -= 1;

        if self.bearingOffStage[self.playerOnTurn] == True and (newPosition == -1 or newPosition == 24):
            self.bearOffCheckers[self.playerOnTurn] += 1
        else:
            playerHit = self.board[newPosition].place(self.playerOnTurn)
            if playerHit:
                self.barPosition[playerHit] += 1
                self.addMoveDirection(oldPosition, playerHit)
                function_Result = 1
        print("move-here")
        self.addMoveDirection(oldPosition, newPosition)

        if self.dice[0] == 0 and self.dice[1] == 0:
            if self.doubles == True:
                self.doubles = False
                self.dice[0] = tempDice
                self.dice[1] = tempDice
            else:
                self.switchPlayers()

        return function_Result

    def printBoard(self):
        for i in range(24):
            print(f'{i} - {self.board[i].checkers}')

    def switchPlayers(self):
        if self.playerOnTurn == self.IRLPlayer:
            self.playerOnTurn = self.OnlinePlayer
        else:
            self.playerOnTurn = self.IRLPlayer
    
    def checkForWin(self):
        if self.bearOffCheckers["pWhite"] == 15:
            self.gameEnd = True
            return "White"
        elif self.bearOffCheckers["pBlack"] == 15:
            self.gameEnd = True
            return "Black"
        return None

    def addMoveDirection(self, oldPosition, newPosition):
        if self.playerOnTurn==self.IRLPlayer:
            return
        direcrionStart = str(oldPosition) + "_"
        direcrionEnd = None
        if newPosition == "pWhite": #if checker is white and has been hit
            direcrionStart += "1"
            direcrionEnd = "outWhite_" #The place where hit White checkers go
            direcrionEnd += str(self.barPosition["pWhite"])
        elif newPosition == "pBlack": #if checker is black and has been hit
            direcrionStart += "1"
            direcrionEnd = "outBlack_" #The place where hit Black checkers go
            direcrionEnd += str(self.barPosition["pBlack"])
        else:
            direcrionStart += str(self.board[oldPosition].checkers + 1)
            direcrionEnd = str(newPosition)
            direcrionEnd += '_'
            direcrionEnd += str(self.board[newPosition].checkers)
        self.moveDirection.append({"From":direcrionStart, "To":direcrionEnd})
        print(self.moveDirection)

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
            return redirect(url_for('index'))
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

# to do
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

@app.route('/createGame', methods=['POST'])
@login_required
def createGame():
    deviceId = request.form['deviceId']
    if current_user.currentGameId != None:
        try:
            connectedDeviceId = gameId_device[current_user.currentGameId]
            if connectedDeviceId != deviceId:
                flash("You are already in game with another device","danger")
                return {'result' : "index"}
            else:
                return {'id' : current_user.currentGameId}
        except:
            pass
            
    device = Device.query.filter_by(deviceId = deviceId).first()
    if device is None or (device.status != "connected" and device.status != "inGame"):

        flash("There is no avaliable device with that Id","danger")
        return {'result' : "index"}
    timeSinceLastDeviceUpdate = datetime.now() - device.lastOnline
    if device.lastOnline == None :
        flash("There is no avaliable device with that Id","danger")
        return {'result' : "index"}
    elif timeSinceLastDeviceUpdate.total_seconds() > 6.0:
        flash("There is no avaliable device with that Id","danger")
        return {'result' : "index"}
    game_id = str(uuid.uuid4())
    print(game_id)
    games[game_id] = Game()
    gameId_device[game_id] = deviceId

    for i in range(20):
        sleep(1)
        if games[game_id].deviceReady == True:
            current_user.currentGameId = game_id;
            db_session.commit()
            return {'id' : game_id}
    # data = {'game_id': game_id}
    # socketio.emit("gameStart", data, to=device_socket[deviceId])
    games.pop(game_id)
    gameId_device.pop(game_id)

    flash("Coucld not connect to the selected device. Try again later","danger")
    return {'result' : "index"}
    

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

@app.route("/delete/<gameId>", methods = ['GET'])
def deleteGame(gameId):
    games.pop(gameId)
    gameId_device.pop(gameId)
    current_user.currentGameId = None
    db_session.commit()
    return redirect(url_for('index'))

@app.route('/ajaxDiceRow/<game_id>', methods = ['GET'])
def ajaxDiceRow(game_id):
    print("here----------------------------------------------------------------------")
    if games[game_id].dice[0] == 0 and games[game_id].dice[1] == 0:  
        games[game_id].dice = rowDice()
        if games[game_id].dice[0] == games[game_id].dice[1]:
            games[game_id].doubles = True
        
        turnPossible = True

        if games[game_id].turnPossible() == -1:
            games[game_id].switchPlayers()
            turnPossible = False
            games[game_id].doubles = False
        print("Game id = ")
        print(game_id)
        socketio.emit("diceResult",  {'dice' : games[game_id].dice, 'turnPossible' : turnPossible, 'currPlayer' : games[game_id].playerOnTurn}, to=game_id)
        return {'dice' : games[game_id].dice, 'turnPossible' : turnPossible, 'currPlayer' : games[game_id].playerOnTurn}
    else:
        return {'dice' : games[game_id].dice, 'currPlayer' : games[game_id].playerOnTurn}


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

    win = games[game_id].checkForWin()
    gameEnd = False
    if win != None:
        gameEnd = True

    return {'allowed':allowed, 'hitt':hitt, 'dice':games[game_id].dice, 'currPlayer' : games[game_id].playerOnTurn, 'gameEnd' : gameEnd, 'winer' : win}

# ------------------------------------------------------------------------------

@app.route("/deviceUpdate", methods=['GET'])
def deviceUpdate():
    deviceId = request.args.get('deviceId')
    connectingDevice = Device.query.filter_by(deviceId=deviceId).first()

    if connectingDevice is None:
        abort(404)
    else:
        if connectingDevice.status != "connected" and connectingDevice.status != "inGame":
            connectingDevice.status = "connected"
        connectingDevice.lastOnline = datetime.now()
        db_session.commit()

    try:
        if connectingDevice.status != "inGame":
            connectingDevice.status = "inGame"
            db_session.commit()
        gameId = list(gameId_device.keys())[list(gameId_device.values()).index(deviceId)]
        return jsonify(gameId = gameId)
    except:
        pass
    return {}
    
@app.route("/getGameData", methods=['GET'])
def getGameData():
    deviceId = request.args.get('deviceId')
    gameId = request.args.get('gameId')
    connectingDevice = Device.query.filter_by(deviceId=deviceId).first()
    if connectingDevice is None:
        abort(404)

    output = {}
    try:
        if connectingDevice.status != "inGame":
            connectingDevice.status = "inGame"
            db_session.commit()
        gameId = list(gameId_device.keys())[list(gameId_device.values()).index(deviceId)]
        output["gameId"] = gameId
        output["playerOnTurn"] = games[gameId].playerOnTurn
        if len(games[gameId].moveDirection) != 0:
            temp = games[gameId].moveDirection[:]
            games[gameId].moveDirection.clear()
            output['move'] = temp
        if games[gameId].dice != [0, 0]:
            output['dice'] = games[gameId].dice
    except:
        pass

    return output

@app.route("/confirmGameStart", methods=['GET'])
def confirmGameStart():
    deviceId = request.args.get('deviceId')
    gameId = request.args.get('gameId')
    device = Device.query.filter_by(deviceId=deviceId).first()
    
    if device is None:
        abort(404)

    try:
        if gameId_device[gameId] != deviceId:
            abort(404)
    except:
        return abort(404)
    games[gameId].deviceReady = True
    return jsonify(
        gameId=gameId,
        playerOnTurn=games[gameId].playerOnTurn,
        playerColor=games[gameId].IRLPlayer,
    )

# ------------------------------------------------------------------------------

@app.route('/shortTask')
def short_running_task():
  start = datetime.now()
  return 'Started at {0}, returned at {1}'.format(start, datetime.now())

# a long running tasks that returns after 30s
@app.route('/longTask')
def long_running_task():
  start = datetime.now()
  sleep(30)
  return 'Started at {0}, returned at {1}'.format(start, datetime.now())

# ------------------------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        return render_template("index.html")
    else:
        return render_template("index_for_non_users.html")

def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

@app.route('/shutdown', methods=['GET'])
def shutdown():
    shutdown_server()
    return 'Server shutting down...'

def processPhotos():
    return 0

if __name__ == '__main__':
    socketio.run(app)