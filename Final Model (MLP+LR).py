import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import shap
import streamlit as st

from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import VotingClassifier
from scipy.stats import shapiro

from sklearn.model_selection import train_test_split,cross_val_score

from sklearn.model_selection import RandomizedSearchCV,StratifiedKFold, GridSearchCV

from sklearn.model_selection import cross_validate
from sklearn.metrics import (accuracy_score, roc_auc_score, precision_score,average_precision_score,
                             recall_score, f1_score, confusion_matrix,auc,
                             ConfusionMatrixDisplay, classification_report, roc_curve,make_scorer,roc_auc_score)

from scipy.stats import spearmanr
from imblearn.over_sampling import SMOTE
from collections import Counter
from sklearn.preprocessing import MinMaxScaler
import pickle
import joblib
from sklearn.utils import resample
from sklearn.model_selection import learning_curve


class PredictionModel:
    def __init__(self):
        self.df = pd.read_csv("./Pima Indians diabetes.csv")
        # Rename the column 'Outcome' to 'Diabetes'
        self.df.rename(columns={'Outcome': 'Diabetes'}, inplace=True)
        self.df.rename(columns={'DiabetesPedigreeFunction': 'DPF'}, inplace=True)
        self.df_1 = self.df.copy()
        # Assuming 'Diabetes' is the target variable and the rest are predictors
        self.X_1 = self.df_1.drop(columns=['Diabetes'])  # Independent variables
        self.y_1 = self.df_1['Diabetes']  # Target variable
        # Data Scaling
        self.scaler = MinMaxScaler()
        self.X_1_scaled = self.scaler.fit_transform(self.X_1)
        self.pca = PCA(n_components=8)
        self.pca_features = self.pca.fit_transform(self.X_1_scaled)
        # Fit PCA Features 
        self.X_train_PCA, self.X_temp_PCA, self.y_train_PCA, self.y_temp_PCA = train_test_split(self.pca_features, self.y_1, test_size=0.3, random_state=42,stratify=self.y_1)
        self.X_val_PCA, self.X_test_PCA, self.y_val_PCA, self.y_test_PCA = train_test_split(self.X_temp_PCA, self.y_temp_PCA, test_size=0.5, random_state=42,stratify=self.y_temp_PCA)
        self.X_train_PCA = self.scaler.fit_transform(self.X_train_PCA)
        self.X_test_PCA = self.scaler.transform(self.X_test_PCA)
        self.X_val_PCA = self.scaler.transform(self.X_val_PCA)
        #Apply SMOTE Techqiue
        self.smote = SMOTE(random_state=42)
        self.X_train_smote_1, self.y_train_smote_1 = self.smote.fit_resample(self.X_train_PCA, self.y_train_PCA)
        # Intialise MLP Model
        self.mlp_final = MLPClassifier(alpha=0.001, batch_size=64, early_stopping=True,
        hidden_layer_sizes=(5,), learning_rate_init=0.01,
        max_iter=500, random_state=200,activation='relu',
        validation_fraction=0.2,tol=0.0001,solver='adam')
        self.mlp_final_model = self.mlp_final.fit(self.X_train_smote_1, self.y_train_smote_1)
        # Use the predicted probabilities from the MLP model on the resampled training data
        self.mlp_final_output = self.mlp_final_model.predict_proba(self.X_train_smote_1)
        # Intialise LR Model
        self.lr_model_final = LogisticRegression(penalty='l2', C=0.001,solver='liblinear', max_iter=100, random_state=42,fit_intercept=True,class_weight='balanced')
        self.lr_model_final.fit(self.mlp_final_output, self.y_train_smote_1)
        # Create a Voting Classifier to combine MLP+LR
        self.voting_mlp_lr_model_final = VotingClassifier(estimators=[('mlp', self.mlp_final_model), ('lr', self.lr_model_final)], voting='soft')
        # Fit the Voting Classifier : MLP + LR
        self.voting_mlp_lr_model_final.fit(self.X_train_smote_1, self.y_train_smote_1)
        #Perform Prediction on MLP+LR
        self.y_test_prob_mlp_lr_final = self.voting_mlp_lr_model_final.predict_proba(self.X_test_PCA)[:, 1]  
        self.y_test_pred_mlp_lr_final = self.voting_mlp_lr_model_final.predict(self.X_test_PCA)  
        # Model Serialization
        with open('voting_classifier_mlp_lr_final.pkl', 'wb') as f:
            pickle.dump(self.voting_mlp_lr_model_final, f)
        # Loading the model from the pickle file
        with open('voting_classifier_mlp_lr_final.pkl', 'rb') as f:
            loaded_model = pickle.load(f)
        
        # Risk Threshold = 0.47
        self.fpr, self.tpr, self.thresholds = roc_curve(self.y_test_PCA, self.y_test_prob_mlp_lr_final)
        self.roc_auc = auc(self.fpr, self.tpr)        
        self.gmeans = np.sqrt(self.tpr * (1 - self.fpr))
        self.ix = np.argmax(self.gmeans)
        self.best_threshold = self.thresholds[self.ix]


    # Define a function for Model Evaluation
    def test_eval(self,clf_model, X_test, y_test, algo='Model', sampling=None,
              precision=[], recall=[], F1score=[], AUCROC=[], AUCPRC=[],
              resample=[], Sensitivity=[], Specificity=[], model_names=[]):
        # Test set prediction
        y_prob = clf_model.predict_proba(X_test)
        y_pred = clf_model.predict(X_test)

        # Compute confusion matrix
        cm = confusion_matrix(y_test, y_pred)
        tn, fp, fn, tp = cm.ravel()

        # Append model name to model_names list
        model_names.append(algo)

        # Calculate metrics
        precision_val = precision_score(y_test, y_pred)
        recall_val = recall_score(y_test, y_pred)
        f1score_val = f1_score(y_test, y_pred)
        aucroc_val = roc_auc_score(y_test, y_prob[:,1])
        sensitivity_val = recall_val  
        specificity_val = tn / (tn + fp) if (tn + fp) > 0 else 0
        aucprc_val = average_precision_score(y_test, y_prob[:, 1])
        g_mean_val = (sensitivity_val * specificity_val) ** 0.5

        # Append results to lists
        precision.append(precision_val)
        recall.append(recall_val)
        F1score.append(f1score_val)
        AUCROC.append(aucroc_val)
        AUCPRC.append(aucprc_val)
        resample.append(sampling)
        Sensitivity.append(sensitivity_val)
        Specificity.append(specificity_val)

    def predict_diabetes_risk_from_user_input(self, age, bmi, pregnancies, glucose, insulin, blood_pressure, DiabetesPedigreeFunction, SkinThickness):
        """
        Predicts diabetes risk based on user input and the trained model.

        Args:
            age (float): Age of the user.
            bmi (float): BMI value of the user.
            pregnancies (float): Number of pregnancies.
            glucose (float): Glucose level.
            insulin (float): Insulin level.
            blood_pressure (float): Blood pressure value.
            DiabetesPedigreeFunction (float): Diabetes pedigree function value.
            SkinThickness (float): Skin thickness measurement.

        Returns:
            dict: A dictionary containing probability and risk category (High/Low Risk).
        """
        # Create the feature array from user input
        features = np.array([[age, bmi, pregnancies, glucose, insulin, blood_pressure, DiabetesPedigreeFunction, SkinThickness]])

        # Use the trained model to predict the probability of diabetes risk
        probabilities = self.voting_mlp_lr_model_final.predict_proba(features)[:, 1]

        # Convert probability to percentage
        probability_percentage = probabilities[0] * 100

        # Classify as High Risk or Low Risk based on the threshold
        categories = np.where(probabilities >= self.best_threshold, "High Risk", "Low Risk")

        # Return the result as a dictionary
        result = {
            "Probability(%)": round(probability_percentage, 2),
            "Category": categories[0]
        }

        return result

model_instance = PredictionModel()

# Title of the app
st.title("Diabetes Risk Prediction")
    
# Get user inputs
age = st.number_input("Age", min_value=0, max_value=120, value=25)
bmi = st.number_input("BMI", min_value=10.0, max_value=100.0, value=30.0)
pregnancies = st.number_input("Pregnancies", min_value=0, max_value=20, value=2)
glucose = st.number_input("Glucose", min_value=0, max_value=300, value=90)
insulin = st.number_input("Insulin", min_value=0, max_value=900, value=85)
blood_pressure = st.number_input("Blood Pressure", min_value=0, max_value=200, value=80)
DiabetesPedigreeFunction = st.number_input("Diabetes Pedigree Function", min_value=0.0, max_value=2.5, value=0.5)
SkinThickness = st.number_input("Skin Thickness", min_value=0, max_value=100, value=30)
    

# When user presses the button to get the result
if st.button("Predict Risk"):
    result = model_instance.predict_diabetes_risk_from_user_input(
        age=age,
        bmi=bmi,
        pregnancies=pregnancies,
        glucose=glucose,
        insulin=insulin,
        blood_pressure=blood_pressure,
        DiabetesPedigreeFunction=DiabetesPedigreeFunction,
        SkinThickness=SkinThickness
    )
    st.write(f"Diabetes Risk Prediction: {result['Category']}")
    st.write(f"Probability: {result['Probability(%)']}%")








        
        



        
  



