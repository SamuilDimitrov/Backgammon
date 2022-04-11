var socket = io();
var game_id = $( "#game_id" ).attr("name");
var old_pos;
var target;
var new_pos;
var currPlayer;

function drag(ev) {
    old_pos = ev.target.parentNode.id;
    target = ev.target.id;
    ev.dataTransfer.setData("text", target);
}

function dragErr(ev) {
    old_pos = null;
    target = null;
}
    
function allowDrop(ev) {
    ev.preventDefault();
}
    
function drop(ev) {
    ev.preventDefault();
    game_id = $( "#game_id" ).attr("name");
    console.log(ev);
    let image = ev.dataTransfer.getData("text");
    let element = ev.target;
    let al = false;
    new_pos = ev.target.id;
    if (old_pos == null){
        return -1
    }
    if (new_pos.includes("text")) {
        new_pos = ev.target.parentNode.id;
    }
    $.ajax({
        url: "/ajaxMove",
        method: "POST",
        data: {
          game_id: game_id,
          old_pos: old_pos,
          new_pos: new_pos,
        },
        async: true,
    }).done(function (data) {
        al = data.allowed;
        currPlayer = data.currPlayer;
        if (al) {
            hitt = data.hitt;
            var checker = document.getElementById(image);
            if (hitt) {
                var content = ev.target.innerHTML;
                ev.target.innerHTML = '';
                if(checker.classList.contains('Black')){
                    var temp = document.getElementById('wHitt').innerHTML
                    temp = temp + content
                    document.getElementById('wHitt').innerHTML = temp; 
                }
                else if(checker.classList.contains('White')){
                    var temp = document.getElementById('bHitt').innerHTML
                    temp = temp + content
                    document.getElementById('bHitt').innerHTML = temp; 
                }
            }
            ev.target.appendChild(checker);
            showDices(data);
            changePlayer(data);
        }
        if (data.gameEnd){
            document.getElementById('ScreenAll').innerHTML = "<h1> Player " + data.winer + " wins!!! </h1>"; 
        }
    });
}

function diceRow() {
    game_id = $("#game_id").attr("name");
    console.log("dice");
    $.ajax({
      url: "/ajaxDiceRow/" + game_id,
      method: "GET",
      success: function (data) {
        showDices(data);
      },
    });
    return true;
};

function showDices(data) {
    dice = data.dice;
    turnPossible = data.turnPossible;
    document.getElementById('dice_1').src = (dice[0] > 0) ? '/static/images/dices/k1_' + dice[0] + '.png' : document.getElementById('dice_1').innerHTML = '';
    document.getElementById('dice_2').src = (dice[1] > 0) ? '/static/images/dices/k2_' + dice[1] + '.png' : document.getElementById('dice_2').innerHTML = '';
    document.getElementById('diceButton').style.visibility = ("{{OnlinePlayer}}" == data.currPlayer && (dice[1] == 0 && dice[0] == 0)) ? "visible" : "hidden";
    console.log(dice);
    if (turnPossible == false){
        setTimeout(function () {
            document.getElementById('dice_1').src = document.getElementById('dice_1').innerHTML = '';
            document.getElementById('dice_2').src = document.getElementById('dice_2').innerHTML = '';
            changePlayer(data);
        }, 5000);
    }
};

function changePlayer(data){
    currPlayer = data.currPlayer;
    document.getElementById("currPlayer").innerHTML = "Player on turn:" + currPlayer;
    // NodeList.prototype.forEach = Array.prototype.forEach;
    // if (currPlayer == "pWhite"){
    //     document.getElementById('wHitt').querySelectorAll('div.White').forEach((function (x) { x.1("draggable", "true"); x.setAttribute("ondragstart", "drag(event)"); }))
    //     document.getElementById('bHitt').querySelectorAll('div.Black').forEach((function (x) { x.setAttribute("draggable", "false"); x.setAttribute("ondragstart", "dragErr(event)"); }))
    //     document.querySelectorAll('div.point>div.White').forEach((function (x) { x.setAttribute("draggable", "true"); x.setAttribute("ondragstart", "drag(event)"); }))
    //     document.querySelectorAll('div.point>div.Black').forEach((function (x) { x.setAttribute("draggable", "false"); x.setAttribute("ondragstart", "dragErr(event)"); }))
    // }else{
    //     document.getElementById('bHitt').querySelectorAll('div.Black').forEach((function (x) { x.setAttribute("draggable", "true"); x.setAttribute("ondragstart", "drag(event)"); }))
    //     document.getElementById('wHitt').querySelectorAll('div.White').forEach((function (x) { x.setAttribute("draggable", "false"); x.setAttribute("ondragstart", "dragErr(event)"); }))
    //     document.querySelectorAll('div.point>div.Black').forEach((function (x) { x.setAttribute("draggable", "true"); x.setAttribute("ondragstart", "drag(event)"); }))
    //     document.querySelectorAll('div.point>div.White').forEach((function (x) { x.setAttribute("draggable", "false"); x.setAttribute("ondragstart", "dragErr(event)"); }))
    // }
};

function moveChecker(data){
    var oldPosition = data.oldPos;
    var newPosition = data.newPos;
    var start = document.getElementById(oldPosition);
    var end = document.getElementById(newPosition);
    end.appendChild(start.firstElementChild);
};

socket.on("connect", () => {
    console.log("just connected the index page");
    socket.emit("join", {
        "game_id": $("#game_id").attr("name")
    });
});

socket.on("message", function (msg) {
    console.log(msg);
});

socket.on("diceResult", function (data) {
    showDices(data);
});

socket.on("game_end", function (data) {
    // to-do
});

socket.on("moveChecker", function (data) {
    moveChecker(data)
});

socket.on("guests_names", function (data) {
});
