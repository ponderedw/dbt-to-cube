{% docs __overview__ %}

# Welcome to DbtEducationalDataProject

A comprehensive educational data analytics project built with dbt, featuring 45 interconnected models that analyze student performance, faculty effectiveness, financial metrics, and institutional operations.

## Here's what makes dbt powerful:

**Lineage Tracking** - Every transformation is fully documented — you can trace the entire data flow from the original source all the way to the dashboard or application that consumes the final (gold) data.

**Testing** - Built-in data quality checks ensure reliability. Tests in dbt are defined separately, allowing you to validate any SQL logic. If a test fails, dbt automatically prevents downstream models from building, protecting your pipeline integrity.

**Modularity** - Reusable models and macros promote the DRY (Don't Repeat Yourself) principle — you write logic once and reuse it across projects. This brings the power of functional programming concepts into data transformation.

**Documentation** - dbt automatically generates rich documentation for your entire project — including models, lineage, and tests. As you can see here, all of this was created automatically by dbt, not manually coded.

## Model Architecture

The project follows a strict three-layer hierarchy:

| Layer | Count | Purpose |
|-------|-------|---------|
| **Staging** (`stg_*`) | 12 models | Raw data cleaning and standardisation |
| **Intermediate** (`int_*`) | 12 models | Complex business logic and cross-domain joins |
| **Marts** | 21 models | Polished, analytics-ready tables for BI and reporting |

## From dbt to Cube.js to Superset — Automatically

This project is connected to **dbt-cube-sync**, a pipeline tool that reads dbt's generated artifacts (`manifest.json`, `catalog.json`) and automatically configures the full analytics stack with zero manual BI setup.

### Why dbt-cube-sync?

🔄 **One definition, everywhere** — Metrics defined once in dbt YAML flow automatically to Cube.js measures and then to Superset calculated metrics. No divergence between warehouse logic and dashboard numbers.

📝 **Descriptions travel with the data** — Column descriptions you write here in dbt YAML appear directly as Superset column descriptions. Update the description in dbt, rerun the pipeline, and Superset reflects the change.

⚡ **No manual BI configuration** — New mart models with a `meta.metrics` block go from dbt YAML → Cube.js schema → Superset dataset fully automatically, with correct column types, descriptions, and metrics.

🔁 **Incremental sync** — Only models whose SQL or YAML changed since the last run are re-processed. The pipeline stays fast regardless of project size.

### The Pipeline

```
dbt run + dbt docs generate
          ↓
  manifest.json / catalog.json
          ↓
  dbt-cube-sync dbt-to-cube   →   Cube.js schemas (.js)
          ↓
  dbt-cube-sync cube-to-bi    →   Superset datasets
                                  (columns + metrics + descriptions)
```

### Defining Metrics in dbt YAML

Mart models that include a `meta.metrics` block are eligible for sync:

```yaml
models:
  - name: course_performance_summary
    config:
      meta:
        metrics:
          average_course_gpa:
            type: avg
            sql: avg_grade_points
            title: "Average Course GPA"
            description: "Average grade points achieved across all enrolled students"
          total_course_enrollments:
            type: sum
            sql: total_enrollments
            title: "Total Course Enrollments"
```

## Navigation

You can use the **Project** and **Database** navigation tabs on the left side of the window to explore the models in your project.

**Project Tab**: Mirrors the directory structure of your dbt project — all models including those imported from dbt packages.

**Database Tab**: Exposes your models as a database explorer, showing tables and views grouped into schemas. Ephemeral models are not shown here as they do not exist in the database.

## Graph Exploration

Click the blue icon on the bottom-right corner to view the lineage graph of your models.

On model pages you will see immediate parents and children of the model you are exploring. Use the **Expand** button at the top-right of the lineage pane to see the full upstream and downstream graph.

Once expanded, use `--select` and `--exclude` model selection syntax to filter the graph.

{% enddocs %}
