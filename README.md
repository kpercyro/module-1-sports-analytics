# Module 1 - Sports Analytics

To run this code, clone this repo on VS Code or download this repo as a .zip package. Ensure all Excel CSV files have also been downloaded.

### Wheelchair rugby data
##### Player data
- player identifier
- disability rating (0-3.5 with increments of 0.5)

##### Stint data
- game_id
- home team
- away team
- length of stint (minutes)
- home team goals
- away team goals
- home players (4)
- away players (4)

### Part 1: Machine learning
##### Data cleaning and analysis
1. calculating relevant player statistics
2. breaking data down to player-stint level

##### Random forest
1. split and trained data with RF
2. cross validation to enhance performance
3. output predicted player scores

###### Input: Wheelchair rugby data (in Data folder)
###### Output: Player's predicted scores (player_scores)

##### To run:
- install pandas
- Jupyter notebook requirements installed

### Part 2: Optimization
- Binary integer programming model to pick the lineup that maximizes the total lineup score adjusted for fatigue and strategy
- Intakes data from the Streamlit Coach Dashboard as parameters for the Gurobi BIP model and outputs the optimization results back to the dashboard for the coach to view
- The Gurobi model is automatically executed when the user clicks the `Start Game` or `Optimize` or `End+Save` buttons on the Streamlit dashboard.

### Part 3: Streamlit Dashboard
To run the Streamlit dashboard, open this project repo in VS Code then in the VS Code terminal, type `streamlit run app.py` and click enter. This should navigate you to the Streamlit dashboard on your browser tab. Once you complete this step, follow the steps in the next section to interact with this dashboard.

##### Streamlit Dashboard Steps
Imagine you are the coach of a murderball team. Your goal is to input the stats about your players (i.e., availability) and use this dashboard to optimize your lineup given the current game situation. Follow the steps below to simulate how this works in a game:
1. Start by selecting the country you are coaching from the dropdown. By default, it is set to Argentina.
2. In the Players section, toggle the red checkbox beside each player to indicate whether or not this player can be considered for the optimal lineup.
3. Next, in the Current Stint Lineup section, under any of the four slots, use the dropdown to select players who you wish to pre-select for the lineup. The optimization model will make sure to include these players in the lineup recommendation and determine the rest of the players.
4. Click the `Optimize` button to execute the Gurobi model in the backend. Now you can see the dashboard shows the optimizer recommended lineup and objective value.
5. Start the game by clicking the `Start Game` button. Start the first stint by clicking the `Start Stint` Button in the Current Stint Runtime section. Once a stint is over, click the `End+Save` button and see how the optimizer adjusts the lineup or objective value.
6. As the game progresses, continue updating the scoreboard. As more stints go on and the scores grow, you are bound to see the lineup change significantly and energy bars decrease.
7. To stop recording data, click the `Stop Game` button and then `Clear/Reset` button. Or you can refresh the tab.
