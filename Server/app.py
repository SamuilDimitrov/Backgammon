import os
from unittest import result
import uuid
import random
import json
from datetime import datetime, timedelta
from time import sleep
import cv2 as cv
import numpy as np

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

@socketio.on('disconnect')
def on_disconnect():
    print("Someone is on_disconnected")

@socketio.on('message')
def handleMessage(msg):
    print('Message:', str(msg))
    send(msg)

@socketio.on('join')
def on_join(data):
    client_nubmer = random.randint(1000, 100000)
    username = "Board #: " + str(client_nubmer)
    game_id = data['game_id']    
    join_room(game_id)
    emit("guests_names", {"board" : username}, to=game_id)

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
            return -1
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
        self.playerOnTurn = "pBlack"
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
                # self.switchPlayers()
                pass
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

@app.route('/uploadPhoto', methods=['POST'])
def uploadPhoto():
    deviceId = request.args.get('deviceId')
    files = request.files
    print(files)
    if 'imageFile' not in request.files:
        return 'there is no imageFile in form!'
    print ("file found")
    file = request.files['imageFile']
    if file:
        filename = file.filename
        name = filename[:len(filename)-4] + "_" + deviceId + filename[len(filename)-4:]
        print(name)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], name))

    try:
        gameId = list(gameId_device.keys())[list(gameId_device.values()).index(deviceId)]
        result = processPhoto(name, gameId)
        if result == -1: #image can not be open
            print("BAD_IMG")
            return "BAD_IMG"
        elif result == -2:
            print("ILLEGAL_MOVE")
            return "ILLEGAL_MOVE"
        print("OK")
        return "OK"
    except:
        print("NO_GAME_FOUND")
        return "NO_GAME_FOUND"
    
#get the avarege brightness of a checker
def checkerColor(src1, center): 
    x = center[1]
    y = center[0]
    avg = 0
    count = 0

    for i in range(x - 10, x + 11):
        for j in range(y - 10, y + 11):
            count += 1
            avg += src1[i, j]
    
    return (avg/count)

# Detect on which point the checker is siting on 
def checkerPosition(arr, startIndex, endIndex, coordinate): 
    # Algorithm - Binary search
    order = ""
    if (arr[0] - arr[1]) > 0:   # see if order is ascending or descending
        order = "descending"
    else:
        order = "ascending"
    if endIndex >= startIndex:
        mid = startIndex + ((endIndex - startIndex) // 2)
        # If element is present at the middle itself
        temp = abs(coordinate - arr[mid])
        if temp <= 25:
            return mid
        # If element is before the mid
        elif arr[mid] > coordinate:
            if order == "ascending":
                return checkerPosition(arr, startIndex, mid-1, coordinate)
            else:
                return checkerPosition(arr, mid + 1, endIndex, coordinate)
        # If element is past the mid
        else:
            if order == "descending":
                return checkerPosition(arr, startIndex, mid-1, coordinate)
            else:
                return checkerPosition(arr, mid + 1, endIndex, coordinate)
    else:
        # Element is not present in the array
        return -1

#get board possitions from photo
def processPhoto(filename, gameId):
    photo_path = UPLOAD_FOLDER +"\\" + filename;
    try:
        src = cv.imread(photo_path)
    except:
        print("here")
        return -1

    resized = cv.resize(src, (1200, 900), interpolation=cv.INTER_LINEAR) #resize img from 1600x1200 to 1200x900

    gray = cv.cvtColor(resized, cv.COLOR_BGR2GRAY) # turn img in black and white

    gray = cv.medianBlur(gray, 5) #blur img

    #detect curcles
    rows = gray.shape[0]
    circles = cv.HoughCircles(gray, cv.HOUGH_GRADIENT, 1, rows / 16,
                                param1=100, param2=20,
                                minRadius=10, maxRadius=50)

    #set up point coordinates
    points_X_1_12 = [1039, 967, 896, 824, 753, 681, 479, 407, 336, 264, 193, 121]
    points_X_13_24 = [111, 183, 254, 326, 397, 469, 671, 743, 814, 886, 957, 1029]
    points_Y = []

    board = [BoardPosition() for i in range(24)]    # temp board of checker positions form photo
    white = []
    black = []

    if circles is not None: 
        circles = np.uint16(np.around(circles))
        for i in circles[0, :]:
            # circle center
            center = (i[0], i[1])
            
            #determine color of checker
            checkerColor = checkerColor(gray, center)
            if checkerColor > 100:
                checkerColor = "pWhite"
                white.append(i)
            else:
                checkerColor = "pBlack"
                black.append(i)

            #   determine the positions of all checkers
            point = -1
            if(i[1] > 450):
                point = checkerPosition(points_X_13_24, 0, len(points_X_13_24) - 1, i[0])
                if point != -1:
                    point += 12
            else:
                point = checkerPosition(points_X_1_12, 0, len(points_X_1_12) - 1 , i[0])

            if point == -1:
                return -2 # incocert possition of checkers

            #   Check for mixed checkr on a point
            if board[point].place(checkerColor) == -1: 
                return -2 # incocert possition of checkers
        
        return checkMoves(board, gameId)

    else:
        print("here2")
        return -1


# compare board position and extract moves
def checkMoves(board, gameId):
    doubles = False
    movedChackersInPoint = {}
    pointsWithChanges = []
    nubmerOfCheckersMoved = 0 # from all points
    
    if games[gameId].dice[0] == games[gameId].dice[1]:
        doubles = True

    for i in range(24):          
        checkersMoved = abs(games[gameId].board[i].checkers - board[i].checkers) #checkers moved from the current point
        
        #switch checker color but kept number of checkers
        if games[gameId].board[i].player != board[i].player and board[i].player != None:
            if games[gameId].board[i].checkers > 2:
                return -2
            else:
                checkersMoved += 1
            
        if checkersMoved > 0 or (games[gameId].board[i].player != board[i].player and board[i].player != None):
            pointsWithChanges.append(i)
            movedChackersInPoint[i] = checkersMoved
            nubmerOfCheckersMoved += checkersMoved

            # moved more Checkers than the max allowed from one point
            if doubles == False and checkersMoved > 2: # normal dice trow
                return -2
            elif doubles == True and checkersMoved > 4: # rowed doubles
                return -2
            if doubles == False and nubmerOfCheckersMoved > 4: # normal dice trow
                return -2
            elif doubles == True and checkersMoved > 4: # rowed doubles
                return -2

    if nubmerOfCheckersMoved == 0:
        return -2

    # one checker moved twice 
    if len(pointsWithChanges) == 2:
        # check if move is allowed
        if abs(pointsWithChanges[0] - pointsWithChanges[1]) == (games[gameId].dice[0] + games[gameId].dice[1]):
            if games[gameId].moveChecker(pointsWithChanges[0], pointsWithChanges[0] + games[gameId].dice[0]) == -1:
                if games[gameId].moveChecker(pointsWithChanges[0], pointsWithChanges[0] + games[gameId].dice[1]) == -1:
                    return -2
                else:
                    games[gameId].moveChecker(pointsWithChanges[0] + games[gameId].dice[0], pointsWithChanges[1])
            else:
                games[gameId].moveChecker(pointsWithChanges[0] + games[gameId].dice[1], pointsWithChanges[1])
            socketio.emit("moveChecker",  {'oldPos' : "point_"  + pointsWithChanges[0], 'newPos' : "point_"  + pointsWithChanges[1]}, to=gameId)
            return 0  
        else:
            return -2
    else:
        if doubles == True:
            for i in range(4):
                dice = games[gameId].dice[0]
                startPoint = pointsWithChanges[0] + dice
                while (1):
                    if pointsWithChanges[startPoint] in movedChackersInPoint:
                        #move checker
                        games[gameId].moveChecker(pointsWithChanges[startPoint], pointsWithChanges[0])
                        socketio.emit("moveChecker",  {'oldPos' : "point_"  +pointsWithChanges[0] , 'newPos' : "point_"  + pointsWithChanges[startPoint]}, to=gameId)
                        # check if all checkers were moved
                        movedChackersInPoint[startPoint] -= 1
                        if movedChackersInPoint[startPoint] <= 0:
                            movedChackersInPoint.pop(startPoint)
                            pointsWithChanges.remove(pointsWithChanges[startPoint])
                        # check if all checkers were moved
                        movedChackersInPoint[pointsWithChanges[0]] -= 1
                        if movedChackersInPoint[pointsWithChanges[0]] <= 0:
                            movedChackersInPoint.pop(pointsWithChanges[0])
                            pointsWithChanges.remove(pointsWithChanges[0])
                        break
                    # chck if the middle point is free
                    elif games[gameId].board[startPoint].player != board[i].player and board[startPoint].player != None:
                        return -2
                    else:
                        startPoint += dice
                        i += 1
                    # no possible starting position found
                    if i >= 4:
                        return -2
            return 0
        else:
            for i in range(2):
                dice = games[gameId].dice[0]
                if games[gameId].dice[0] != 0:
                    startPoint = pointsWithChanges[0] + games[gameId].dice[0]
                    if startPoint in movedChackersInPoint:
                        games[gameId].moveChecker(pointsWithChanges[0], startPoint)
                    else:
                        startPoint = pointsWithChanges[0] + games[gameId].dice[1]
                        if startPoint in movedChackersInPoint:
                            games[gameId].moveChecker(pointsWithChanges[0], startPoint)
                        else:
                            return -2
                else:
                    startPoint = pointsWithChanges[0] + games[gameId].dice[1]
                    if startPoint in movedChackersInPoint:
                        games[gameId].moveChecker(pointsWithChanges[0], startPoint)
                    else:
                        return -2
                socketio.emit("moveChecker",  {'oldPos' : "point_"  + pointsWithChanges[startPoint], 'newPos' : "point_"  + pointsWithChanges[0]}, to=gameId)
                # check if all checkers were moved
                movedChackersInPoint[startPoint] -= 1
                if movedChackersInPoint[startPoint] <= 0:
                    movedChackersInPoint.pop(startPoint)
                    pointsWithChanges.remove(pointsWithChanges[startPoint])
                movedChackersInPoint[pointsWithChanges[0]] -= 1
                if movedChackersInPoint[pointsWithChanges[0]] <= 0:
                    movedChackersInPoint.pop(pointsWithChanges[0])
                    pointsWithChanges.remove(pointsWithChanges[0])
            return 0
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
    if games[game_id].dice[0] == 0 and games[game_id].dice[1] == 0:  
        games[game_id].dice = rowDice()
        if games[game_id].dice[0] == games[game_id].dice[1]:
            games[game_id].doubles = True
        
        turnPossible = True

        if games[game_id].turnPossible() == -1:
            games[game_id].switchPlayers()
            turnPossible = False
            games[game_id].doubles = False
        socketio.emit("diceResult",  {'dice' : games[game_id].dice, 'turnPossible' : turnPossible, 'currPlayer' : games[game_id].playerOnTurn}, to=game_id)
        return {'dice' : games[game_id].dice, 'turnPossible' : turnPossible, 'currPlayer' : games[game_id].playerOnTurn}
    else:
        return {'dice' : games[game_id].dice, 'currPlayer' : games[game_id].playerOnTurn}

@app.route('/ajaxMove', methods = ['POST'])
def ajax_request():
    old_pos_string = request.form['old_pos']
    new_pos_string = request.form['new_pos']
    game_id = request.form['game_id']

    if games[game_id].playerOnTurn != games[game_id].OnlinePlayer:
        return {'allowed' : False, 'currPlayer' : games[game_id].playerOnTurn}

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
        socketio.emit("moveChecker",  {'oldPos' : old_pos_string, 'newPos' : new_pos_string}, to=game_id)
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

@app.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        return render_template("index.html")
    else:
        return render_template("index_for_non_users.html")

if __name__ == '__main__':
    socketio.run(app)