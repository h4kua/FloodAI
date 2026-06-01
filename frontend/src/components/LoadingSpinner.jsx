export default function LoadingSpinner({ message = "Memuat data..." }) {
  return (
    <div className="loading-wrap">
      <div className="spinner" />
      <span>{message}</span>
    </div>
  );
}
