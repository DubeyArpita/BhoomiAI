"""Evaluate document-level semantic search against independently labelled questions.

Example labels:
[
  {"question":"How does DILRMP work?",
   "relevant_filenames":["official_dilrmp_guidelines.pdf"],
   "state":"","district":""}
]
Never claim an evaluation result until labels and this script have actually run.
"""
import argparse
import json
import os
import statistics
import time
import urllib.parse
import urllib.request


def evaluate(records, endpoint, token, k):
    if not records:
        raise ValueError("Supply at least one held-out labelled query.")
    precisions, recalls, reciprocal_ranks, latencies=[],[],[],[]
    for row in records:
        truth=set(row["relevant_filenames"])
        if not truth:
            raise ValueError("Every test question requires at least one relevant filename.")
        params=urllib.parse.urlencode(
            {"q":row["question"],"limit":min(20,4*k),
             "state":row.get("state",""),"district":row.get("district","")})
        request=urllib.request.Request(
            endpoint.rstrip("/")+"/search?"+params,
            headers={"Authorization":"Bearer "+token})
        started=time.perf_counter()
        with urllib.request.urlopen(request,timeout=180) as response:
            result=json.load(response)
        latencies.append((time.perf_counter()-started)*1000)
        # Index returns chunks; rank first occurrence of each document.
        documents=list(dict.fromkeys(s["filename"] for s in result["results"]))[:k]
        hits=[doc in truth for doc in documents]
        precisions.append(sum(hits)/k)
        recalls.append(len(truth.intersection(documents))/len(truth))
        reciprocal_ranks.append(next((1/i for i,hit in enumerate(hits,1) if hit),0))
    return {"queries":len(records),"k":k,
            "precision_at_k":round(statistics.mean(precisions),4),
            "recall_at_k":round(statistics.mean(recalls),4),
            "mrr_at_k":round(statistics.mean(reciprocal_ranks),4),
            "mean_latency_ms":round(statistics.mean(latencies),2),
            "median_latency_ms":round(statistics.median(latencies),2),
            "note":"Document-level scoring after deduplicating chunk-ranked filenames. "
                   "Retrieval is limited to the top min(20,4k) chunks."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("labels_json")
    parser.add_argument("--url",default="http://127.0.0.1:8000")
    parser.add_argument("-k",type=int,default=5)
    parser.add_argument("--output",default="retrieval_evaluation.json")
    args=parser.parse_args()
    if not 1<=args.k<=10:
        parser.error("k must be between 1 and 10.")
    token=os.getenv("BHOOMIAI_TOKEN")
    if not token:
        parser.error("Set BHOOMIAI_TOKEN to a current local login token.")
    with open(args.labels_json,encoding="utf-8") as handle:
        records=json.load(handle)
    metrics=evaluate(records,args.url,token,args.k)
    with open(args.output,"w",encoding="utf-8") as handle:
        json.dump(metrics,handle,indent=2)
    print(json.dumps(metrics,indent=2))


if __name__=="__main__":
    main()
