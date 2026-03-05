# Arbiter Classifier

**3-Model Architecture with Reasoning-Based Arbitration**

## Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                         IMAGE INPUT                              │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │           PARALLEL            │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │   GEMINI 2.5    │             │    GPT-4o       │
    │   + Reasoning   │             │   + Reasoning   │
    └────────┬────────┘             └────────┬────────┘
             │                               │
             └───────────┬───────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │      COMPARE        │
              └─────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
    ┌────▼────┐                    ┌─────▼─────┐
    │  AGREE  │                    │ DISAGREE  │
    │  (~70%) │                    │  (~30%)   │
    └────┬────┘                    └─────┬─────┘
         │                               │
         │                               ▼
         │                    ┌─────────────────┐
         │                    │    ARBITER      │
         │                    │   (o3 Model)    │
         │                    │                 │
         │                    │ Reviews both    │
         │                    │ reasonings and  │
         │                    │ picks winner    │
         │                    └────────┬────────┘
         │                             │
         └─────────────┬───────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  FINAL OUTPUT   │
              └─────────────────┘
```

## Key Features

1. **Reasoning Extraction**: Both models provide prediction + reasoning
2. **Efficient**: Arbiter only called for ~30% of cases (disagreements)
3. **High Confidence**: Agreed predictions are used directly
4. **Transparent**: Full reasoning chain stored for analysis

## Files

```
arbiter_classifier/
├── config/
│   └── settings.env              # All configuration
├── prompts/
│   ├── gemini_reasoning_v1.txt   # Gemini prompt with reasoning
│   ├── openai_reasoning_v1.txt   # OpenAI prompt with reasoning
│   └── arbiter_v1.txt            # Arbiter decision prompt
├── results/
├── batch_arbiter.py              # Main classification
├── generate_report.py            # Generate metrics
├── run_pipeline.py               # Run everything
├── requirements.txt
└── README.md
```

## Usage

```bash
cd arbiter_classifier
export TURING_API_KEY="your_key"
python run_pipeline.py
```

## Configuration

Edit `config/settings.env`:

```env
# Models
GEMINI_MODEL=gemini-2.5-pro
OPENAI_MODEL=gpt-4o
ARBITER_MODEL=o3

# Prompt versions
GEMINI_PROMPT_VERSION=1
OPENAI_PROMPT_VERSION=1
ARBITER_PROMPT_VERSION=1

# Processing
PARALLEL_WORKERS=5
PIPELINE_VERSION=1
```

## Output

`results/arbiter_v{X}_metrics.xlsx`:
- **Summary**: Individual model accuracy vs final arbiter accuracy
- **Arbiter Decisions**: Each disagreement with reasoning from both models
- **All Results**: Complete per-image breakdown

## Expected Improvements

- **Better than either model alone**: Arbiter picks the better reasoning
- **Transparent decisions**: Know exactly why each prediction was made
- **Efficient**: Only ~1.3x API cost vs single model (arbiter only on disagreements)
