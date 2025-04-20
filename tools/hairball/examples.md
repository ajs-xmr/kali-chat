## Curl Search Examples

### Basic search

`curl "http://localhost:5000/api/search?q=lex+situs"`

`curl "http://localhost:5000/api/search?q=lex+situs+immovable+property"`

`curl "http://localhost:5000/api/search?q='lex+AND+(situs+OR+immovable)'"`

`curl "http://localhost:5000/api/search?q=\"lex+situs\""`

### 5 results per request

`curl "http://localhost:5000/api/search?q=lex+situs&n_results=5"`

### Retrieve full document by ID

`curl "http://localhost:5000/api/document/fd0f03556ab28b68081d871511efa074"`
