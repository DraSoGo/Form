from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1,max_length=4000)]
Number = Annotated[float, Field(ge=0,le=20000,allow_inf_nan=False)]
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')
class SuggestedChange(Strict):
    kind: Literal['nutrition','workout']
    expected_version: int = Field(ge=1)
    before: dict
    proposed: dict
    reason: Text
    evidence: Text
class Food(Strict):
    name: str = Field(min_length=1,max_length=200)
    amount: str = Field(min_length=1,max_length=200)
class NutritionEstimate(Strict):
    foods: list[Food] = Field(min_length=1,max_length=20)
    calories: Number
    protein: Number
    carbs: Number
    fat: Number
    fiber: Number
    sugar: Number | None = None
    sodium: Number | None = None
    calories_low: Number
    calories_high: Number
    confidence: Literal['low','medium','high']
    uncertainty: Text
    @model_validator(mode='after')
    def range_valid(self):
        if not self.calories_low <= self.calories <= self.calories_high:
            raise ValueError('Calories must lie within range')
        return self
class DailySummary(Strict):
    summary: Text
    highlights: list[Text] = Field(default_factory=list,max_length=8)
    suggestions: list[SuggestedChange] = Field(default_factory=list,max_length=3)
class WorkoutAnalysis(DailySummary): pass
class BodyTrendAnalysis(DailySummary): pass
class ChatAnswer(DailySummary): pass
class ExerciseMetadata(Strict):
    aliases: list[Annotated[str, Field(min_length=1,max_length=79)]] = Field(default_factory=list,max_length=10)
    primary_muscles: list[Annotated[str, Field(min_length=1,max_length=79)]] = Field(default_factory=list,max_length=10)
    secondary_muscles: list[Annotated[str, Field(min_length=1,max_length=79)]] = Field(default_factory=list,max_length=10)
    classification: Literal['compound','isolation']
SCHEMAS = dict(food=NutritionEstimate, daily=DailySummary, workout=WorkoutAnalysis,body=BodyTrendAnalysis,chat=ChatAnswer,exercise=ExerciseMetadata)
