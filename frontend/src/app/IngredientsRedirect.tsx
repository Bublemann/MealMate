import { Navigate, useLocation, useParams } from 'react-router';

/**
 * The Items tab was the Ingredients tab: an old link or bookmark (/ingredients, /ingredients/<id>,
 * any sub-path) opens the same place under /items, with its query and hash.
 */
export function IngredientsRedirect() {
  const { '*': rest = '' } = useParams();
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: rest ? `/items/${rest}` : '/items', search, hash }} replace />;
}
