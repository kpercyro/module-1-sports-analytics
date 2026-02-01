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
- The Gurobi model is automatically executed when the user clicks the `Start Game` or `Optimize` buttons on the Streamlit dashboard.

### Part 3: Streamlit dashboard
To run the Streamlit dashboard, open this project repo in VS Code then in the VS Code terminal, type `python run app.py` and click enter. This should navigate you to the Streamlit dashboard on your browser tab.
